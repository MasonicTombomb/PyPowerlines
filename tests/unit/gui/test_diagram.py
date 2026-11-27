"""Tests for the network diagram widget."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("PyQt6")

from pypowerlines.gui.diagram import (
    NetworkDiagramWidget,
    _Edge,
    _loading_color,
    _spring_layout,
)
from pypowerlines.io import load_study
from pypowerlines.solver import solve_scenario

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "north_wales" / "study.yaml"


def test_spring_layout_is_deterministic() -> None:
    bus_ids = ["a", "b", "c", "d"]
    edges: list[_Edge] = []
    a = _spring_layout(bus_ids, edges)
    b = _spring_layout(bus_ids, edges)
    assert a == b


def test_spring_layout_separates_connected_nodes() -> None:
    bus_ids = ["a", "b", "c"]
    # a-b connected; c isolated. The spring should push c away from the pair.
    edges: list[_Edge] = [_Edge("a", "b")]
    pos = _spring_layout(bus_ids, edges, iterations=400)
    # All three positions distinct.
    coords = set(pos.values())
    assert len(coords) == 3


def test_loading_color_bands() -> None:
    assert _loading_color(float("nan")).name() == "#888888"
    assert _loading_color(10).name() == "#2e8b57"  # green
    assert _loading_color(75).name() == "#daa520"  # amber
    assert _loading_color(95).name() == "#e07b1a"  # orange
    assert _loading_color(130).name() == "#c3272b"  # red


def test_set_study_populates_scene(qapp: QApplication) -> None:
    del qapp
    study = load_study(EXAMPLE)
    diagram = NetworkDiagramWidget()
    diagram.set_study(study)
    n_lines = len(study.grid.lines) + len(study.grid.transformers)
    n_buses = len(study.grid.buses)
    # Scene should contain at least one item per edge plus one per bus plus labels.
    scene = diagram.scene()
    assert scene is not None
    assert len(scene.items()) >= n_buses + n_lines


def test_set_result_recolours_edges(qapp: QApplication) -> None:
    del qapp
    study = load_study(EXAMPLE)
    scenario = next(s for s in study.scenarios if s.id == "winter_peak")
    result = solve_scenario(study, scenario)
    diagram = NetworkDiagramWidget()
    diagram.set_study(study)
    diagram.set_result(result)
    # Pick an edge from the result; its tooltip should reflect loading.
    assert diagram._edge_items, "diagram has no edges"
    first_br = next(br for br in result.branches if br.kind == "line")
    key = (first_br.from_bus, first_br.to_bus)
    edge = diagram._edge_items.get(key) or diagram._edge_items.get((key[1], key[0]))
    assert edge is not None
    assert "loading:" in edge.toolTip()
