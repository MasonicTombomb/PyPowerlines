"""Tests for :mod:`pypowerlines.physics.lineparams`.

Worked example from PPL-CH-001 CS-05 to CS-09 using twin ACSR Zebra on
an L6 400 kV tower (flat phases, 11 m spacing, 0.4 m bundle spacing):

* Rdc at 20 °C: 0.0674 Ω/km  (per bundle sub-conductor)
* Rac at 75 °C: 0.0833 Ω/km  (per bundle sub-conductor, with skin effect)
* Reactance: 0.334 Ω/km  (per phase)
* Shunt susceptance: 3.354 µS/km  (per phase)
"""

from __future__ import annotations

import math

import pytest

from pypowerlines.library import builtin_library
from pypowerlines.model import ConductorType
from pypowerlines.physics import lineparams


@pytest.fixture
def twin_zebra():
    """Twin ACSR Zebra from the built-in library."""
    return builtin_library().get_conductor("ACSR Zebra")


@pytest.fixture
def l6_tower():
    return builtin_library().get_tower("L6_400kV")


def test_rdc_at_20c_matches_cs05(twin_zebra):
    # Per sub-conductor Rdc at 20 °C is the library value (CS-05).
    assert math.isclose(
        lineparams.rdc_per_m(twin_zebra, 20.0),
        twin_zebra.r20_ohm_per_m,
        rel_tol=1e-12,
    )


def test_rdc_rises_with_temperature(twin_zebra):
    # ~22 % increase at 75 °C per CS-05.
    r75 = lineparams.rdc_per_m(twin_zebra, 75.0)
    r20 = lineparams.rdc_per_m(twin_zebra, 20.0)
    assert r75 / r20 == pytest.approx(1 + 0.00403 * 55, rel=1e-6)


def test_rac_includes_skin_effect(twin_zebra):
    # CS-06: Rac at 75 °C about 0.0833 Ω/km.
    rac_per_km = lineparams.rac_per_m(twin_zebra, 75.0, 50.0) * 1e3
    assert rac_per_km == pytest.approx(0.0833, rel=5e-3)


def test_reactance_matches_cs08(twin_zebra, l6_tower):
    x_per_km = lineparams.series_reactance_per_m(twin_zebra, l6_tower, 50.0) * 1e3
    assert x_per_km == pytest.approx(0.334, rel=2e-2)


def test_susceptance_matches_cs09(twin_zebra, l6_tower):
    b_per_km = lineparams.shunt_susceptance_per_m(twin_zebra, l6_tower, 50.0) * 1e3
    assert b_per_km == pytest.approx(3.354e-6, rel=2e-2)


def test_gmr_bundle_matches_cs07(twin_zebra):
    gmr = lineparams.bundle_gmr_m(twin_zebra)
    # CS-07: 68.1 mm for twin Zebra at 0.4 m spacing.
    assert gmr == pytest.approx(0.0681, rel=5e-3)


def test_req_bundle_matches_cs07(twin_zebra):
    req = lineparams.bundle_req_m(twin_zebra)
    # CS-07: 75.7 mm.
    assert req == pytest.approx(0.0757, rel=5e-3)


def test_phase_gmd_cs08(l6_tower):
    gmd = lineparams.phase_gmd_m(l6_tower)
    # CS-08: 13.86 m for 11 m flat spacing.
    assert gmd == pytest.approx(13.86, rel=2e-3)


def test_single_conductor_fallback():
    single = ConductorType(name="X", diameter_m=0.02, r20_ohm_per_m=1e-4, sub_conductors=1)
    gmr = lineparams.bundle_gmr_m(single)
    assert gmr == pytest.approx(0.7788 * 0.01)
