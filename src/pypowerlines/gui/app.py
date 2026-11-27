"""Qt application bootstrap."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Launch the PyPowerlines workbench.

    Raises
    ------
    SystemExit
        If PyQt6 is not installed. Install the GUI extra:
        ``pip install pypowerlines[gui]``.
    """
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: PLC0415 -- deferred import gates GUI extra
    except ModuleNotFoundError as exc:  # pragma: no cover - import-guard
        raise SystemExit(
            "PyQt6 is not installed. Install the GUI extra: pip install 'pypowerlines[gui]'",
        ) from exc

    from .main_window import MainWindow  # noqa: PLC0415 -- imports PyQt6 transitively

    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("PyPowerlines")
    app.setOrganizationName("PyPowerlines")
    window = MainWindow()
    window.show()
    return app.exec()
