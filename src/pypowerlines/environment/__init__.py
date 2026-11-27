"""Weather-zone resolution.

This module decides what environmental conditions a given
:class:`~pypowerlines.model.Span` sees in a given
:class:`~pypowerlines.model.Scenario`. It applies the zone offsets
(temperature, wind multiplier) so that :mod:`pypowerlines.physics.thermal`
receives absolute, already-corrected values.

Air properties (density, viscosity, conductivity) and the wind-angle
factor are not here but in :mod:`pypowerlines.physics.thermal` because
they are a peer module in the architecture layers; keeping all
IEEE 738 helpers on one side of the layer boundary keeps the dependency
graph clean.
"""

from __future__ import annotations

from pypowerlines.model import Scenario, Span, WeatherState, WeatherZone

__all__ = ["resolve_weather"]


def resolve_weather(scenario: Scenario, zone: WeatherZone, span: Span) -> WeatherState:
    """Combine scenario and zone inputs into the weather seen by a span.

    The calculation follows PPL-REF-001 Table 4: the zone's temperature
    offset is added to the scenario ambient and the zone's wind multiplier
    is applied to the scenario wind.

    Parameters
    ----------
    scenario : Scenario
        Scenario-wide base values.
    zone : WeatherZone
        The zone the span belongs to.
    span : Span
        Span whose elevation and azimuth may refine the zone value.

    Returns
    -------
    WeatherState
        Final weather for the thermal model.
    """
    elevation = span.elevation_m if span.elevation_m is not None else zone.elevation_m
    return WeatherState(
        ambient_c=scenario.ambient_c + zone.temperature_offset_k,
        wind_ms=max(scenario.wind_ms * zone.wind_multiplier, 0.0),
        wind_angle_deg=scenario.wind_angle_deg,
        irradiance_wm2=scenario.irradiance_wm2,
        elevation_m=elevation,
        rain_mmh=scenario.rain_mmh,
    )
