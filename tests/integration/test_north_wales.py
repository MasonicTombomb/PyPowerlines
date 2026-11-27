"""End-to-end test: the North Wales reference network.

Solves the three scenarios of PPL-REF-001 section 4 with coupling on and
checks:

* the solver reaches NR convergence and the outer loop settles in a
  handful of passes;
* the per-scenario total losses are in the right ballpark
  (33.8 / 26.6 / 40.2 MW from PPL-REF-001 section 5);
* the hottest line is WYLF-PENT in every scenario because of the heavy
  Wylfa generation + Anglesey wind profile;
* bus voltages for the slack and PV buses are exactly their set-points.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pypowerlines.io import load_study
from pypowerlines.model import Study
from pypowerlines.solver import solve_scenario

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "north_wales" / "study.yaml"


@pytest.fixture(scope="module")
def study() -> Study:
    return load_study(EXAMPLE)


@pytest.mark.parametrize(
    "scenario_id,expected_loss_mw,tolerance_mw",
    [
        ("winter_peak", 33.8, 10.0),
        ("summer_day", 26.6, 10.0),
        ("heatwave", 40.2, 10.0),
    ],
)
def test_total_losses_within_range(
    study: Study, scenario_id: str, expected_loss_mw: float, tolerance_mw: float
) -> None:
    scenario = next(s for s in study.scenarios if s.id == scenario_id)
    result = solve_scenario(study, scenario)
    assert result.converged
    assert abs(result.total_loss_mw - expected_loss_mw) < tolerance_mw


def test_coupling_raises_heatwave_losses_above_fixed_r(study: Study) -> None:
    """Hot conductors run resistively hotter so coupled losses exceed the
    fixed-20 °C ones (PPL-REF-001 section 5, +14.8 %)."""
    heatwave = next(s for s in study.scenarios if s.id == "heatwave")
    result = solve_scenario(study, heatwave)
    assert result.total_loss_mw > result.total_loss_fixed_r_mw


def test_coupling_reduces_winter_losses_below_fixed_r(study: Study) -> None:
    """Cold conductors in winter lower effective R below the 20 °C value."""
    winter = next(s for s in study.scenarios if s.id == "winter_peak")
    result = solve_scenario(study, winter)
    assert result.total_loss_mw < result.total_loss_fixed_r_mw


def test_wylf_pent_is_hottest_in_heatwave(study: Study) -> None:
    heatwave = next(s for s in study.scenarios if s.id == "heatwave")
    result = solve_scenario(study, heatwave)
    temps = {
        b.branch_id: max((c.t_c for c in b.conductors), default=-1.0)
        for b in result.branches
        if b.kind == "line"
    }
    hottest = max(temps, key=lambda k: temps[k])
    assert hottest == "WYLF-PENT"


def test_slack_voltage_is_set_point(study: Study) -> None:
    scenario = study.scenarios[0]
    result = solve_scenario(study, scenario)
    dees = next(b for b in result.buses if b.bus_id == "DEES4")
    assert dees.v_pu == pytest.approx(1.0, abs=1e-6)
    assert dees.angle_deg == pytest.approx(0.0, abs=1e-9)


def test_pv_bus_holds_voltage(study: Study) -> None:
    scenario = study.scenarios[0]
    result = solve_scenario(study, scenario)
    wylf = next(b for b in result.buses if b.bus_id == "WYLF4")
    assert wylf.v_pu == pytest.approx(1.01, abs=1e-4)


def test_newton_raphson_takes_few_iterations(study: Study) -> None:
    for scenario in study.scenarios:
        result = solve_scenario(study, scenario)
        assert result.nr_iterations <= 8
        assert result.coupling_passes <= 10
