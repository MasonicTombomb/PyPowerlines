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
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Final

from pypowerlines import __version__
from pypowerlines._log import configure_logging, get_logger, shutdown_logging
from pypowerlines.errors import (
    InputError,
    ModelError,
    NumericalError,
    PyPowerlinesError,
)
from pypowerlines.io import load_study, write_results
from pypowerlines.library import builtin_library
from pypowerlines.report import format_summary, log_summary
from pypowerlines.solver import solve_scenario

__all__ = ["EXIT_INTERRUPTED", "EXIT_OK", "EXIT_PARTIAL", "build_parser", "main"]

log = get_logger(__name__)

EXIT_OK: Final[int] = 0
"""Exit code for a successful run."""

EXIT_PARTIAL: Final[int] = 3
"""Exit code when at least one scenario failed numerically."""

EXIT_INTERRUPTED: Final[int] = 130
"""Exit code after Ctrl+C (128 + SIGINT, the usual shell convention)."""


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Returns
    -------
    argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="pypowerlines",
        description="Steady-state transmission network simulator with weather-dependent losses.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

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
    parser.set_defaults(log_level="INFO", command=None)

    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run a study and write results")
    run.add_argument("study", type=Path, help="path to study.yaml")
    run.add_argument(
        "--out",
        type=Path,
        default=None,
        help="directory to write results into (default: results/ next to study.yaml)",
    )
    run.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="solve only this scenario id (repeat for several); "
        "default: solve every scenario defined in the study",
    )
    run.add_argument(
        "--no-coupling",
        action="store_true",
        help="disable the electro-thermal outer loop (R fixed at t_start_c)",
    )
    run.add_argument(
        "--relax",
        type=float,
        default=None,
        help="override the coupling relaxation factor w",
    )

    validate = sub.add_parser("validate", help="load and validate the study, then exit")
    validate.add_argument("study", type=Path, help="path to study.yaml")

    lib = sub.add_parser("library", help="inspect the built-in equipment library")
    lib.add_argument(
        "action",
        choices=["list"],
        nargs="?",
        default="list",
        help="what to do",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``pypowerlines`` command and return its exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(level=args.log_level)
    try:
        log.debug("PyPowerlines started.", version=__version__, args=vars(args))
        exit_code = _run(parser, args)
        log.debug("PyPowerlines finished.", exit_code=exit_code)
        return exit_code
    finally:
        shutdown_logging()


def _run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Execute the selected command and map exceptions to exit codes."""
    try:
        return _dispatch(parser, args)

    except InputError as err:
        for problem in err.problems:
            log.log(problem.severity, str(problem), rule=problem.rule, path=problem.path)
        log.error(err.message, code=err.code, **err.fields)
        return err.exit_code

    except ModelError as err:
        log.exception(err.message, code=err.code, **err.context)
        raise

    except PyPowerlinesError as err:
        log.error(err.message, code=err.code, **err.fields)
        log.debug("Traceback of the error above.", exc_info=err)
        return err.exit_code

    except KeyboardInterrupt:
        log.warning("Interrupted by user; stopping.")
        return EXIT_INTERRUPTED

    except Exception:
        log.exception("Unexpected internal error. This is a bug in PyPowerlines.")
        raise


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Dispatch to the selected subcommand."""
    if args.command is None:
        parser.print_help()
        return EXIT_OK
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "library":
        return _cmd_library(args)
    parser.print_help()
    return EXIT_OK


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def _cmd_validate(args: argparse.Namespace) -> int:
    study = load_study(args.study)
    log.info(
        "Study loaded.",
        id=study.id,
        buses=len(study.grid.buses),
        lines=len(study.grid.lines),
        transformers=len(study.grid.transformers),
        scenarios=len(study.scenarios),
    )
    print(
        f"{study.id}: {len(study.grid.buses)} buses, "
        f"{len(study.grid.lines)} lines, "
        f"{len(study.grid.transformers)} transformers, "
        f"{len(study.scenarios)} scenarios -- OK",
    )
    return EXIT_OK


def _cmd_library(args: argparse.Namespace) -> int:
    del args  # unused in v1; reserved for future `library show NAME` dispatch
    lib = builtin_library()
    print("Conductors:")
    for name in sorted(lib.conductors):
        c = lib.conductors[name]
        print(f"  {name:20s} d={c.diameter_m * 1000:.2f} mm  R20={c.r20_ohm_per_m * 1000:.4f} Ω/km")
    print("Towers:")
    for name in sorted(lib.towers):
        print(f"  {name}")
    print("Transformers:")
    for name in sorted(lib.transformers):
        t = lib.transformers[name]
        print(f"  {name:25s} {t.rating_mva} MVA {t.hv_kv}/{t.lv_kv} kV  z={t.z_pct}%")
    return EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    study = load_study(args.study)

    # Apply CLI overrides to solver options.
    options = study.options
    if args.no_coupling:
        options = replace(options, coupling=False)
    if args.relax is not None:
        options = replace(options, relaxation=args.relax)
    study = replace(study, options=options)

    scenarios = study.scenarios
    if args.scenario:
        wanted = set(args.scenario)
        scenarios = tuple(s for s in scenarios if s.id in wanted)
        missing = wanted - {s.id for s in scenarios}
        if missing:
            log.warning("Unknown scenario ids skipped.", ids=sorted(missing))
    if not scenarios:
        log.error("No scenarios to solve.", requested=args.scenario)
        return EXIT_OK

    results = []
    failed = 0
    for scenario in scenarios:
        log.info("Solving scenario.", id=scenario.id, name=scenario.name)
        try:
            results.append(solve_scenario(study, scenario))
        except NumericalError as err:
            log.error(
                "Scenario failed numerically; continuing with the next one.",
                scenario_id=scenario.id,
                code=err.code,
                **err.fields,
            )
            failed += 1

    outdir = args.out or (args.study.parent / "results")
    if results:
        write_results(results, outdir)
        log.info("Results written.", outdir=str(outdir), scenarios=len(results))
        log_summary(study, results)
        sys.stdout.write(format_summary(study, results))

    return EXIT_PARTIAL if failed else EXIT_OK
