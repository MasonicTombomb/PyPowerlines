"""PyQt6 workbench for PyPowerlines.

Opens a study, lets the user pick a scenario, runs the coupled solver
and shows the results in sortable tables. Install with the ``gui``
optional extra and launch via ``pypowerlines-gui`` or
``python -m pypowerlines.gui``.
"""

from __future__ import annotations

from .app import main

__all__ = ["main"]
