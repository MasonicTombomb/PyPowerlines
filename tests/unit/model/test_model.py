"""Tests for the frozen dataclasses in :mod:`pypowerlines.model`."""

from __future__ import annotations

import dataclasses
from math import isclose, pi

import pytest

from pypowerlines.model import (
    Bus,
    ConductorType,
    Grid,
    Line,
    Scenario,
    SolverOptions,
    Span,
    Study,
    TowerType,
    WeatherZone,
)


def test_bus_is_frozen():
    bus = Bus(id="A", name="a", kv=400.0, type="pq")
    with pytest.raises(dataclasses.FrozenInstanceError):
        bus.kv = 275.0  # type: ignore[misc]


def test_line_length_sums_spans():
    tower = TowerType(name="T", phases_m=((-1.0, 0.0), (0.0, 0.0), (1.0, 0.0)))
    cond = ConductorType(name="C", diameter_m=0.02, r20_ohm_per_m=1e-4)
    zone = WeatherZone(id="z", name="z", latitude_deg=53.0)
    a = Bus(id="A", name="a", kv=400.0, type="slack")
    b = Bus(id="B", name="b", kv=400.0, type="pq")
    spans = (
        Span(length_m=10_000.0, tower=tower, conductor=cond, zone=zone),
        Span(length_m=5_000.0,  tower=tower, conductor=cond, zone=zone),
    )
    line = Line(id="L", from_bus=a, to_bus=b, circuits=1, spans=spans)
    assert line.length_m == 15_000.0


def test_grid_bus_index():
    a = Bus(id="A", name="a", kv=400.0, type="slack")
    b = Bus(id="B", name="b", kv=400.0, type="pq")
    grid = Grid(buses=(a, b), lines=(), transformers=(), loads=(), generators=())
    assert grid.bus_index() == {"A": 0, "B": 1}


def test_study_omega():
    a = Bus(id="A", name="a", kv=400.0, type="slack")
    grid = Grid(buses=(a,), lines=(), transformers=(), loads=(), generators=())
    study = Study(
        id="x", name="x", frequency_hz=50.0, base_mva=100.0,
        grid=grid, scenarios=(Scenario(id="s", name="s", ambient_c=0.0, wind_ms=0.0),),
        options=SolverOptions(),
    )
    assert isclose(study.omega, 2 * pi * 50.0)


def test_scenario_overrides_default_empty_dicts():
    s1 = Scenario(id="a", name="a", ambient_c=0.0, wind_ms=0.0)
    s2 = Scenario(id="b", name="b", ambient_c=0.0, wind_ms=0.0)
    s1.gen_p_mw["X"] = 1.0
    assert "X" not in s2.gen_p_mw
