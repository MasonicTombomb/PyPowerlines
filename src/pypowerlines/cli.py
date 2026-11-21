"""Command-line interface for PyPowerlines.

This module is the program's single entry point (PPL-SDS-001 section 6.1).
It owns three jobs that no other module may do:

1. **Parse arguments.** No calculations and no file parsing happen here.
2. **Configure logging.** Console verbosity comes from ``-v`` / ``-q``.
   Library modules only *emit* log records; this is the only place that
   decides where they go.
3. **Map outcomes to exit codes.** Every path through :func:`main` ends in
   exactly one exit code:

   .. list-table::
      :header-rows: 1
      :widths: 15 85

      * - Code
        - Meaning
      * - 0
        - Success: all cases solved (or nothing to do).
      * - 1
        - Unexpected failure, e.g. a :class:`~pypowerlines.errors.ModelError`
          (a bug). The traceback is printed and logged.
      * - 2
        - Input error: nothing was solved. The full list of problems is
          logged. Also used by :mod:`argparse` for command-line usage
          errors.
      * - 3
        - One or more cases failed numerically. Results for the other cases
          are still written.
      * - 130
        - Interrupted by the user (Ctrl+C), following the shell convention
          128 + SIGINT.

Error-handling policy
---------------------
Exceptions are caught **only here**, at the top of the program, and only
the expected ones (PPL-ADR-001: "never bare except"):

* :class:`~pypowerlines.errors.InputError` and the other
  :class:`~pypowerlines.errors.PyPowerlinesError` subclasses are logged with
  their code, cause and remedy, and turned into their ``exit_code``.
* :class:`~pypowerlines.errors.ModelError` and any exception PyPowerlines
  did not anticipate are bugs. They are logged with their traceback (so
  ``run.log.jsonl`` holds it) and then **re-raised**, never swallowed.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Final

from pypowerlines import __version__
from pypowerlines._log import configure_logging, get_logger, shutdown_logging
from pypowerlines.errors import InputError, ModelError, PyPowerlinesError

__all__ = ["EXIT_INTERRUPTED", "EXIT_OK", "build_parser", "main"]

log = get_logger(__name__)

EXIT_OK: Final[int] = 0
"""Exit code for a successful run."""

EXIT_INTERRUPTED: Final[int] = 130
"""Exit code after Ctrl+C (128 + SIGINT, the usual shell convention)."""

# Exit codes 2 and 3 are not repeated here. They live on the exception
# classes (InputError.exit_code, NumericalError.exit_code), so the mapping
# cannot drift out of step with pypowerlines.errors.


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Parser for the ``pypowerlines`` command. Parsed arguments always
        contain ``log_level``, one of ``"DEBUG"``, ``"INFO"`` (default) or
        ``"WARNING"``.
    """
    parser = argparse.ArgumentParser(
        prog="pypowerlines",
        description="Steady-state transmission network simulator with weather-dependent losses.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    # -v and -q contradict each other, so argparse rejects them together.
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v",
        "--verbose",
        dest="log_level",
        action="store_const",
        const="DEBUG",
        help="show debug messages as well as progress",
    )
    verbosity.add_argument(
        "-q",
        "--quiet",
        dest="log_level",
        action="store_const",
        const="WARNING",
        help="show only warnings and errors",
    )
    parser.set_defaults(log_level="INFO")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``pypowerlines`` command.

    Parses the arguments, configures logging for the duration of the
    command, runs it, and turns the outcome into an exit code. Logging is
    always shut down on the way out, so log files are flushed and closed
    even when an exception escapes.

    Parameters
    ----------
    argv : Sequence[str] or None
        Arguments to parse; ``None`` reads them from ``sys.argv``.

    Returns
    -------
    int
        Process exit code. See the module docstring for the meaning of
        each value.

    Raises
    ------
    SystemExit
        From :mod:`argparse` for ``--help``, ``--version`` (code 0) and
        usage errors (code 2). These happen before logging is configured.
    ModelError
        Re-raised after logging: it is a bug and must not be hidden.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(level=args.log_level)
    try:
        log.debug("PyPowerlines started.", version=__version__, args=vars(args))
        exit_code = _run(parser, args)
        log.debug("PyPowerlines finished.", exit_code=exit_code)
        return exit_code
    finally:
        # In ``finally`` so the log is flushed even when _run re-raises.
        shutdown_logging()


def _run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Run the selected command and map exceptions to exit codes.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The parser, used to print help when no command is given.
    args : argparse.Namespace
        The parsed arguments.

    Returns
    -------
    int
        Process exit code.
    """
    try:
        return _dispatch(parser, args)

    except InputError as err:
        # Log every finding at its own severity so each one is a separate,
        # filterable record. Then log the summary with cause and remedy.
        for problem in err.problems:
            log.log(problem.severity, str(problem), rule=problem.rule, path=problem.path)
        log.error(err.message, code=err.code, **err.fields)
        return err.exit_code

    except ModelError as err:
        # A bug: record the traceback in the log file, then let it propagate
        # so Python also prints it and the process exits non-zero.
        log.exception(err.message, code=err.code, **err.context)
        raise

    except PyPowerlinesError as err:
        # Includes NumericalError (exit 3) if one escapes the solver's own
        # per-case handling. The traceback goes to DEBUG only: the coded
        # message, cause and remedy are what the user needs.
        log.error(err.message, code=err.code, **err.fields)
        log.debug("Traceback of the error above.", exc_info=err)
        return err.exit_code

    except KeyboardInterrupt:
        log.warning("Interrupted by user; stopping.")
        return EXIT_INTERRUPTED

    except Exception:
        # Anything else is an unanticipated bug. Log it with the traceback,
        # then re-raise: never turn an unknown failure into a quiet exit code.
        log.exception("Unexpected internal error. This is a bug in PyPowerlines.")
        raise


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Run the command selected on the command line.

    The ``run``, ``validate`` and ``library`` commands (PPL-UG-001
    section 4) will be dispatched from here. Until they exist, the help
    text is printed.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The parser, used to print help.
    args : argparse.Namespace
        The parsed arguments.

    Returns
    -------
    int
        Process exit code.
    """
    log.debug("No command given; printing help.")
    parser.print_help()
    return EXIT_OK
