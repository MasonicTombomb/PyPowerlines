"""Shared fixtures for GUI tests. Force the offscreen Qt platform."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Iterator

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> Iterator[QApplication]:
    """Session-wide QApplication; skips if no Qt platform plugin is available."""
    existing: QApplication | None = QApplication.instance()
    if existing is None:
        try:
            app = QApplication([])
        except Exception as exc:  # pragma: no cover - platform-specific
            pytest.skip(f"Qt platform plugin unavailable: {exc}")
    else:
        assert isinstance(existing, QApplication)
        app = existing
    yield app
