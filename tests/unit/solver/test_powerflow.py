"""Tests for the Newton-Raphson power flow.

A 2-bus toy network: 100 MVA at a lagging 0.95 pf drawn from a slack
through one line. The solved voltage magnitude at the load bus must sit
below 1.0 pu and the mismatch must fall below the tolerance.
"""

from __future__ import annotations

import numpy as np
import pytest

from pypowerlines.errors import PowerFlowDivergence
from pypowerlines.library import builtin_library
from pypowerlines.model import (
    Bus,
    Grid,
    Line,
    Load,
    Scenario,
    SolverOptions,
    Span,
    Study,
    WeatherZone,
)
from pypowerlines.solver.network import build_branches
from pypowerlines.solver.powerflow import solve_powerflow


def _two_bus_study(line_length_km: float = 50.0) -> Study:
    lib = builtin_library()
    zebra = lib.get_conductor("ACSR Zebra")
    tower = lib.get_tower("L6_400kV")

    zone = WeatherZone(id="z", name="z", latitude_deg=53.0, elevation_m=0.0)
    slack = Bus(id="S", name="slack", kv=400.0, type="slack", v_set_pu=1.0)
    load_bus = Bus(id="L", name="load", kv=400.0, type="pq")
    span = Span(length_m=line_length_km * 1000, tower=tower, conductor=zebra, zone=zone)
    line = Line(id="SL", from_bus=slack, to_bus=load_bus, circuits=1, spans=(span,))
    load = Load(id="LD", bus=load_bus, p_mw=100.0, q_mvar=32.9)  # pf 0.95 lagging

    grid = Grid(
        buses=(slack, load_bus),
        lines=(line,),
        transformers=(),
        loads=(load,),
        generators=(),
        zones=(zone,),
    )
    scenario = Scenario(id="s", name="s", ambient_c=15.0, wind_ms=1.0)
    return Study(
        id="two-bus",
        name="two bus",
        frequency_hz=50.0,
        base_mva=100.0,
        grid=grid,
        scenarios=(scenario,),
        options=SolverOptions(),
    )


def test_two_bus_converges():
    study = _two_bus_study()
    branches = build_branches(study)
    p = np.array([0.0, -1.0])  # 100 MW at the load bus, slack free
    q = np.array([0.0, -0.329])
    types = ("slack", "pq")
    v_set = np.array([1.0, 1.0])
    sol = solve_powerflow(study, branches, p, q, types, v_set)
    assert sol.iterations <= 6
    assert sol.max_mismatch_pu < 1e-8
    assert sol.v_mag[0] == pytest.approx(1.0)
    # Load bus voltage drops below 1.0 under lagging load.
    assert 0.9 < sol.v_mag[1] < 1.0


def test_slack_angle_is_zero():
    study = _two_bus_study()
    branches = build_branches(study)
    sol = solve_powerflow(
        study, branches, np.array([0.0, 0.0]), np.array([0.0, 0.0]),
        ("slack", "pq"), np.array([1.0, 1.0]),
    )
    assert sol.v_ang[0] == 0.0


def test_powerflow_diverges_on_overload():
    """Request an absurd power transfer and expect divergence."""
    study = _two_bus_study(line_length_km=400.0)  # very long = high X
    branches = build_branches(study)
    # 10 GW load through a single long circuit = past stability limit.
    p = np.array([0.0, -100.0])
    q = np.array([0.0, -50.0])
    with pytest.raises(PowerFlowDivergence):
        solve_powerflow(study, branches, p, q, ("slack", "pq"), np.array([1.0, 1.0]))
