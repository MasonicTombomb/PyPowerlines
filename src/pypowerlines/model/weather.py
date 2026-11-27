"""Weather state used by the thermal and environment models.

A :class:`WeatherState` is the fully-resolved environmental input for a
single zone at a single instant: the numbers IEEE 738 needs to find the
conductor temperature.

The zone's offsets (see :class:`~pypowerlines.model.WeatherZone`) are
applied here, so :mod:`pypowerlines.physics.thermal` receives absolute
values and does no further zone bookkeeping.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["WeatherState"]


@dataclass(frozen=True, slots=True)
class WeatherState:
    """Environmental conditions at one point in space and time.

    Parameters
    ----------
    ambient_c : float
        Ambient air temperature at the conductor's elevation, °C.
    wind_ms : float
        Wind speed perpendicular component used for convection, m/s.
        The caller has already resolved wind direction against the span
        azimuth (CS-14's :math:`K_{angle}`).
    wind_angle_deg : float, default 90.0
        Angle between the wind and the conductor axis, degrees. 90° is
        perpendicular (maximum cooling).
    irradiance_wm2 : float, default 0.0
        Solar irradiance on the conductor surface, W/m². Zero at night.
    elevation_m : float, default 0.0
        Elevation above sea level, metres. Needed for air density and
        pressure corrections (CS-11, CS-28).
    rain_mmh : float, default 0.0
        Rainfall rate, mm/h. Only used by the corona model today.
    """

    ambient_c: float
    wind_ms: float
    wind_angle_deg: float = 90.0
    irradiance_wm2: float = 0.0
    elevation_m: float = 0.0
    rain_mmh: float = 0.0

    @property
    def ambient_k(self) -> float:
        """Ambient temperature in kelvin, for radiative calculations."""
        return self.ambient_c + 273.15
