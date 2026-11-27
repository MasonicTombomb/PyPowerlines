r"""Study loading and result writing.

Two public entry points:

* :func:`load_study` reads a ``study.yaml`` file (optionally with a
  separate ``grid.yaml`` and one or more ``library/*.yaml``) and returns
  a validated :class:`~pypowerlines.model.Study`. Every schema and
  cross-reference check in PPL-DATA-001 Table 9 that we implement in v1
  is collected into a single :class:`~pypowerlines.errors.InputError`
  before anything numerical runs.

* :func:`write_results` writes a directory of CSV / JSON files from a
  list of :class:`~pypowerlines.solver.SnapshotResult`\s. See
  :mod:`pypowerlines.report` for the row-level details.
"""

from .loader import load_study
from .writer import write_results

__all__ = ["load_study", "write_results"]
