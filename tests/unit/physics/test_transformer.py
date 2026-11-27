"""Tests for :mod:`pypowerlines.physics.transformer`.

PPL-CH-001 CS-20 worked example: 240 MVA transformer, P0 = 150 kW,
Pk = 700 kW. At 180 MVA (0.75 pu), total loss = 543.8 kW.
"""

from __future__ import annotations

import pytest

from pypowerlines.library import builtin_library
from pypowerlines.physics import transformer as t


@pytest.fixture
def sgt():
    return builtin_library().get_transformer("SGT_240MVA_400_132")


def test_loss_matches_cs20(sgt):
    loss_mw = t.loss_mw(sgt, count=1, s_mva=180.0, v_pu=1.0)
    assert loss_mw == pytest.approx(0.5438, rel=1e-3)


def test_loss_doubles_with_two_units_in_parallel(sgt):
    # Same total throughput split between two units: load loss quartered
    # per unit but doubled by the two units = halved; no-load doubles.
    one = t.loss_mw(sgt, count=1, s_mva=180.0, v_pu=1.0)
    two = t.loss_mw(sgt, count=2, s_mva=180.0, v_pu=1.0)
    assert two < one  # halving the load loss dominates


def test_series_impedance_pu_change_of_base(sgt):
    # Nameplate z 15% on 240 MVA. On 100 MVA system base:
    # z_pu = 0.15 * 100 / 240 = 0.0625
    z = t.series_impedance_pu(sgt, base_mva=100.0)
    assert abs(z) == pytest.approx(0.0625, rel=1e-3)


def test_tap_ratio_nominal(sgt):
    assert t.tap_ratio(sgt, 0) == 1.0


def test_tap_ratio_step(sgt):
    # One step is 1.25 %, so tap_pos=+4 gives 1.05.
    assert t.tap_ratio(sgt, 4) == pytest.approx(1.05)
