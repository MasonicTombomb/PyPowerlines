"""Tests for :mod:`pypowerlines.physics.thermal`.

Worked example from PPL-CH-001 CS-11-15 (Zebra at 75 °C, 25 °C ambient,
0.5 m/s perpendicular wind, full sun 1000 W/m²):

* q_c  = 62.5 W/m
* q_r  = 24.2 W/m
* q_s  = 22.9 W/m
* Ampacity per sub-conductor at 75 °C = 875 A
"""

from __future__ import annotations

import pytest

from pypowerlines.library import builtin_library
from pypowerlines.model import WeatherState
from pypowerlines.physics import thermal
from pypowerlines.physics.thermal import (
    _convective_loss_wpm,
    _radiative_loss_wpm,
    _solar_gain_wpm,
)


@pytest.fixture
def zebra():
    # Use the single-conductor variant so the per-bundle math equals the
    # per-sub-conductor numbers in CS-15.
    return builtin_library().get_conductor("ACSR Zebra x1")


@pytest.fixture
def cs15_weather():
    return WeatherState(
        ambient_c=25.0,
        wind_ms=0.5,
        wind_angle_deg=90.0,
        irradiance_wm2=1000.0,
        elevation_m=0.0,
    )


def test_solar_gain_matches_cs12(zebra, cs15_weather):
    q_s = _solar_gain_wpm(zebra, cs15_weather)
    assert q_s == pytest.approx(22.9, rel=2e-2)


def test_radiative_loss_matches_cs13(zebra, cs15_weather):
    q_r = _radiative_loss_wpm(zebra, 75.0, cs15_weather)
    assert q_r == pytest.approx(24.2, rel=3e-2)


def test_convective_loss_matches_cs14(zebra, cs15_weather):
    q_c = _convective_loss_wpm(zebra, 75.0, cs15_weather)
    assert q_c == pytest.approx(62.5, rel=3e-2)


def test_ampacity_matches_cs15(zebra, cs15_weather):
    i = thermal.ampacity(zebra, cs15_weather, t_max_c=75.0)
    # CS-15 says 875 A per sub-conductor.
    assert i == pytest.approx(875.0, rel=5e-2)


def test_conductor_temperature_matches_cs15_reverse(zebra, cs15_weather):
    # CS-15: at 800 A the conductor sits at 68.7 °C.
    t = thermal.conductor_temperature(zebra, 800.0, cs15_weather, circuits=1)
    assert t == pytest.approx(68.7, abs=1.0)


def test_heat_balance_residual_is_zero_at_solution(zebra, cs15_weather):
    t = thermal.conductor_temperature(zebra, 800.0, cs15_weather, circuits=1)
    terms = thermal.heat_terms(zebra, t, 800.0, cs15_weather)
    assert abs(terms.residual) < 1.0  # W/m


def test_air_density_sea_level_50c():
    # CS-11 worked example: 1.0925 kg/m^3 at sea level, 50 C.
    assert thermal.air_density(50.0, 0.0) == pytest.approx(1.0925, rel=1e-3)


def test_air_viscosity_50c():
    assert thermal.air_viscosity(50.0) == pytest.approx(1.9529e-5, rel=1e-3)


def test_wind_angle_factor_is_1_at_perpendicular():
    assert thermal.wind_angle_factor(90.0) == pytest.approx(1.0, abs=5e-3)


def test_wind_angle_factor_falls_at_parallel():
    # ~0.39 at 0° per CS-14 chart.
    assert thermal.wind_angle_factor(0.0) < 0.5


def test_standard_pressure_at_sea_level():
    assert thermal.standard_pressure_pa(0.0) == pytest.approx(101_325.0)


def test_ampacity_drops_with_higher_ambient(zebra):
    cold = WeatherState(ambient_c=5.0, wind_ms=0.5, irradiance_wm2=1000.0)
    hot = WeatherState(ambient_c=35.0, wind_ms=0.5, irradiance_wm2=1000.0)
    assert thermal.ampacity(zebra, cold, t_max_c=75.0) > thermal.ampacity(
        zebra, hot, t_max_c=75.0
    )
