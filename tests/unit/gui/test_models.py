"""Tests for the Qt table models wrapping SnapshotResult."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt

from pypowerlines.gui.models import (
    branch_model,
    bus_model,
    conductor_model,
    populate_from_result,
    transformer_model,
)
from pypowerlines.io import load_study
from pypowerlines.solver import solve_scenario

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "north_wales" / "study.yaml"


def test_empty_models_have_zero_rows(qapp: QApplication) -> None:
    del qapp
    for m in (bus_model(), branch_model(), conductor_model(), transformer_model()):
        assert m.rowCount() == 0
        assert m.columnCount() > 0


def test_populate_fills_every_tab(qapp: QApplication) -> None:
    del qapp
    study = load_study(EXAMPLE)
    scenario = next(s for s in study.scenarios if s.id == "winter_peak")
    result = solve_scenario(study, scenario)

    buses = bus_model()
    branches = branch_model()
    conductors = conductor_model()
    transformers = transformer_model()
    populate_from_result(
        buses=buses,
        branches=branches,
        conductors=conductors,
        transformers=transformers,
        result=result,
    )

    assert buses.rowCount() == len(result.buses)
    assert branches.rowCount() == len(result.branches)
    assert transformers.rowCount() == len(result.transformers)
    expected_conductor_rows = sum(len(br.conductors) for br in result.branches)
    assert conductors.rowCount() == expected_conductor_rows


def test_data_formats_floats(qapp: QApplication) -> None:
    del qapp
    study = load_study(EXAMPLE)
    scenario = next(s for s in study.scenarios if s.id == "winter_peak")
    result = solve_scenario(study, scenario)
    buses = bus_model()
    buses.set_rows(list(result.buses))
    # Column 1 is V (pu) formatted with {:.4f}
    idx = buses.index(0, 1)
    text = buses.data(idx, Qt.ItemDataRole.DisplayRole)
    assert isinstance(text, str)
    assert "." in text and len(text.split(".")[1]) == 4


def test_header_uses_display_role(qapp: QApplication) -> None:
    del qapp
    buses = bus_model()
    header = buses.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
    assert header == "Bus"
    row_header = buses.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.DisplayRole)
    assert row_header == 1
