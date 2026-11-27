"""Tests for :mod:`pypowerlines.environment`."""

from __future__ import annotations

import pytest

from pypowerlines.environment import resolve_weather
from pypowerlines.library import builtin_library
from pypowerlines.model import Scenario, Span, WeatherZone


@pytest.fixture
def zone():
    return WeatherZone(
        id="snowdonia",
        name="Snowdonia",
        latitude_deg=53.0,
        elevation_m=300.0,
        temperature_offset_k=-3.0,
        wind_multiplier=1.5,
    )


@pytest.fixture
def span(zone):
    lib = builtin_library()
    return Span(
        length_m=1000.0,
        tower=lib.get_tower("L6_400kV"),
        conductor=lib.get_conductor("ACSR Zebra"),
        zone=zone,
    )


def test_zone_offset_applied(span, zone):
    scenario = Scenario(id="w", name="w", ambient_c=10.0, wind_ms=2.0)
    ws = resolve_weather(scenario, zone, span)
    assert ws.ambient_c == pytest.approx(7.0)  # 10 + (-3)
    assert ws.wind_ms == pytest.approx(3.0)  # 2.0 * 1.5


def test_elevation_defaults_to_zone(span, zone):
    scenario = Scenario(id="w", name="w", ambient_c=0.0, wind_ms=0.0)
    ws = resolve_weather(scenario, zone, span)
    assert ws.elevation_m == 300.0


def test_wind_cannot_go_negative(span, zone):
    scenario = Scenario(id="w", name="w", ambient_c=0.0, wind_ms=-1.0)
    ws = resolve_weather(scenario, zone, span)
    assert ws.wind_ms == 0.0


def test_scenario_irradiance_passes_through(span, zone):
    scenario = Scenario(id="w", name="w", ambient_c=0.0, wind_ms=0.0, irradiance_wm2=850.0)
    ws = resolve_weather(scenario, zone, span)
    assert ws.irradiance_wm2 == 850.0
