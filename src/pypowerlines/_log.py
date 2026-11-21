"""Logging and message-catalogue integration with :mod:`annunciator`.

All logging in PyPowerlines goes through the ``annunciator`` library
(PPL-ADR-001, ADR-006). This private module is the single place where the
package talks to annunciator directly. The rest of the code base uses the
small API defined here, so a change in annunciator only needs to be absorbed
in one file.

Responsibilities
----------------
* **Message catalogue.** :data:`MESSAGES` is the PyPowerlines catalogue of
  coded messages (prefix ``PPL``). Each entry has a code, a text template,
  a probable cause and a remedy. The same definitions drive log records,
  exception messages (see :mod:`pypowerlines.errors`) and documentation.
* **Loggers.** :func:`get_logger` returns structured loggers inside the
  ``pypowerlines`` logger namespace.
* **Configuration.** :func:`configure_logging` / :func:`shutdown_logging`
  set up and tear down the console output and the ``run.log.jsonl`` file.
  Only :mod:`pypowerlines.cli` should call them.
* **Provenance.** :func:`record_provenance` writes the reproducibility
  record (versions, platform, input hashes, solver options) to the log.

Message code numbering
----------------------
Codes have the form ``PPL-<severity letter>-<number>``. Numbers are grouped
by area so the code alone says where a message comes from:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Range
     - Area
   * - 0001-0099
     - Run lifecycle, logging and provenance (this module)
   * - 0100-0199
     - Input loading and validation (:class:`~pypowerlines.errors.InputError`)
   * - 0200-0299
     - Numerical failures (:class:`~pypowerlines.errors.NumericalError`)
   * - 0900-0999
     - Internal defects (:class:`~pypowerlines.errors.ModelError`)

A message number is never reused, even after a message is removed, so that
old log files stay unambiguous.

Library etiquette
-----------------
Importing PyPowerlines never configures logging. A :class:`logging.NullHandler`
is attached to the ``pypowerlines`` logger so that a program that uses
PyPowerlines as a library, and has no logging set up, sees no stray output.
Handlers are only installed when :func:`configure_logging` is called.

Examples
--------
>>> from pypowerlines._log import get_logger
>>> log = get_logger("pypowerlines.solver.example")
>>> log.name
'pypowerlines.solver.example'
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import annunciator
from annunciator import LogConfig, MessageCatalogue, Severity, StructuredLogger

from ._version import __version__

__all__ = [
    "MESSAGES",
    "PROVENANCE",
    "ROOT_LOGGER_NAME",
    "configure_logging",
    "get_logger",
    "record_provenance",
    "shutdown_logging",
]


# ---------------------------------------------------------------------------
# Namespace
# ---------------------------------------------------------------------------

ROOT_LOGGER_NAME: Final[str] = "pypowerlines"
"""Name of the top-level logger that every PyPowerlines logger sits under.

:func:`configure_logging` attaches its handlers to this logger only, so
log output from other libraries (numpy, pandas, ...) is not mixed in.
"""

# Standard library-etiquette: with no handler configured, Python's "last
# resort" handler would print WARNING+ records to stderr. A NullHandler
# keeps a library import silent until the application opts in.
logging.getLogger(ROOT_LOGGER_NAME).addHandler(logging.NullHandler())


# ---------------------------------------------------------------------------
# Message catalogue
# ---------------------------------------------------------------------------

MESSAGES: Final[MessageCatalogue] = MessageCatalogue(
    "PPL",
    "PyPowerlines messages",
    # Registration is global in annunciator. ``replace=True`` lets this
    # module be re-imported (e.g. by test tooling or importlib.reload)
    # without failing with ANN-E-0105 "prefix already registered".
    replace=True,
)
"""The PyPowerlines message catalogue (prefix ``PPL``).

Messages are defined next to the code that uses them: run-level messages
below, exception messages in :mod:`pypowerlines.errors`. Use
``annunciator.explain("PPL-E-0100")`` to print the full definition of a
code.
"""

# -- Run lifecycle, logging and provenance (0001-0099) ----------------------

PROVENANCE: Final[str] = MESSAGES.define(
    1,
    Severity.NOTICE,
    "Provenance recorded for PyPowerlines {pypowerlines_version}.",
    cause="A study run started; this record makes it reproducible.",
    remedy="No action needed. The 'manifest' field holds the full record.",
    category="run",
    since="0.1.0",
).code
"""Code ``PPL-N-0001``: the provenance record of a run.

Emitted by :func:`record_provenance`.
"""

_PROVENANCE_PACKAGES: Final[tuple[str, ...]] = (
    "numpy",
    "scipy",
    "pandas",
    "pydantic",
    "PyYAML",
)
"""Distributions whose versions are recorded in every provenance record.

These are the runtime dependencies that can change numerical results.
annunciator's own version is always recorded by
:func:`annunciator.collect_manifest`.
"""


# ---------------------------------------------------------------------------
# Loggers
# ---------------------------------------------------------------------------


def get_logger(name: str) -> StructuredLogger:
    """Return the structured logger for a module.

    Thin wrapper around :func:`annunciator.get_logger`. Call it once at
    module level with ``__name__``::

        log = get_logger(__name__)
        log.info("Solving snapshot.", timestamp=ts)
        log.event(SOME_CODE, span_id="S-12")

    Keyword arguments to the log methods become structured fields in
    ``run.log.jsonl``, which is far easier to filter than values pasted
    into the message text.

    Parameters
    ----------
    name : str
        Dotted logger name. It should start with ``"pypowerlines"``
        (which ``__name__`` does in package modules). Loggers outside that
        namespace still work but do not reach the handlers installed by
        :func:`configure_logging`.

    Returns
    -------
    annunciator.StructuredLogger
        The logger. The same object is returned for the same name.

    Notes
    -----
    Physics functions must stay pure (PPL-ADR-001 coding standards): do not
    log inside hot loops. Log once per case or per solver pass instead, or
    use the logger's ``once`` / ``every`` / ``throttle`` methods.
    """
    return annunciator.get_logger(name)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def configure_logging(
    level: str = "INFO",
    log_file: str | Path | None = None,
    *,
    console: bool = True,
) -> LogConfig:
    """Install the console and log-file handlers for a run.

    Intended to be called exactly once, by :mod:`pypowerlines.cli`, before
    any work starts (PPL-SDS-001 section 6.1). Calling it again replaces
    the previous configuration.

    Parameters
    ----------
    level : str, default "INFO"
        Minimum severity to record, e.g. ``"DEBUG"``, ``"INFO"``,
        ``"WARNING"``. The CLI maps ``-v`` / ``-q`` to this.
    log_file : str or pathlib.Path or None, default None
        Path of the structured log, normally ``<results>/run.log.jsonl``.
        Written as JSON lines (one event per line) in annunciator's
        format, as required by PPL-DATA-001 section 9. ``None`` disables
        the file.
    console : bool, default True
        Whether to print human-readable progress to the terminal.

    Returns
    -------
    annunciator.LogConfig
        The configuration now in effect.

    Raises
    ------
    annunciator.ConfigurationError
        If ``level`` is not a known severity name.

    See Also
    --------
    shutdown_logging : Flush and remove the handlers again.
    """
    return annunciator.configure(
        level=level,
        logger_name=ROOT_LOGGER_NAME,
        console=console,
        file=None if log_file is None else str(log_file),
        file_format="json",
        # One log file per run, stored with that run's results, so rotation
        # would only split a single run's record across files.
        rotate="none",
        # Record exceptions that escape everything (e.g. a ModelError), so
        # the traceback ends up in run.log.jsonl and not only on stderr.
        install_hooks=True,
    )


def shutdown_logging() -> None:
    """Flush and close all handlers installed by :func:`configure_logging`.

    Call at the end of a CLI command (ideally in a ``finally`` block) so
    that ``run.log.jsonl`` is complete before the process exits. Safe to
    call when logging was never configured.
    """
    annunciator.shutdown()


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def record_provenance(info: Mapping[str, Any]) -> dict[str, Any]:
    """Log the reproducibility record of a run and return it.

    Builds a manifest with :func:`annunciator.collect_manifest` (Python,
    platform, package versions, git revision, command line), adds the
    PyPowerlines version and the caller's ``info``, and logs it as a single
    ``PPL-N-0001`` event whose ``manifest`` field holds the whole record.

    Parameters
    ----------
    info : Mapping[str, Any]
        Run-specific data that is needed to reproduce the results, per the
        provenance block of PPL-DATA-001 section 9, e.g.::

            {
                "schema_version": "1.0",
                "inputs": {"grid.yaml": "sha256:a1b2..."},
                "options": {"coupling": True, "relaxation": 1.0},
            }

        Values must be JSON-serialisable. Stored under the ``"extra"`` key
        of the manifest.

    Returns
    -------
    dict[str, Any]
        The complete manifest that was logged, so the report module can
        write the same data into ``summary.json``.

    Notes
    -----
    The user's login name is deliberately **not** recorded (it is personal
    data). The host name and working directory are, because they are
    usually needed to locate the inputs of an old run.
    """
    manifest = annunciator.collect_manifest(
        packages=_PROVENANCE_PACKAGES,
        git=True,
        extra=dict(info),
    )
    manifest["pypowerlines_version"] = __version__
    get_logger(ROOT_LOGGER_NAME).event(
        PROVENANCE,
        pypowerlines_version=__version__,
        manifest=manifest,
    )
    return manifest
