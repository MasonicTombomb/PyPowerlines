"""Smoke tests for the workbench main window."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QMessageBox

from pypowerlines.gui.main_window import MainWindow

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "north_wales" / "study.yaml"


def test_window_starts_empty(qapp: QApplication) -> None:
    del qapp
    w = MainWindow()
    assert w._study is None
    assert w._scenario_combo.count() == 0
    assert not w._run_button.isEnabled()


def test_load_study_populates_scenarios(qapp: QApplication) -> None:
    del qapp
    w = MainWindow()
    w._load_study(EXAMPLE)
    assert w._study is not None
    assert w._scenario_combo.count() == len(w._study.scenarios)
    assert w._run_button.isEnabled()


def test_run_solves_scenario_and_updates_tables(qapp: QApplication) -> None:
    del qapp
    w = MainWindow()
    w._load_study(EXAMPLE)
    # Winter peak is the first scenario in the example study.
    w._scenario_combo.setCurrentIndex(0)
    w._on_run_clicked()
    assert w._buses.rowCount() > 0
    assert w._branches.rowCount() > 0
    assert "Coupled total loss" in w._loss_label.text()


def test_load_bad_path_keeps_study_none(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    # The error dialog is modal; stub it so headless tests don't block.
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: None)
    w = MainWindow()
    w._load_study(tmp_path / "nope.yaml")
    assert w._study is None
