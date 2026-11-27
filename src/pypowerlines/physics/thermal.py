r"""Conductor steady-state thermal model (IEEE 738-2012).

Given a span's conductor, the weather and either a current or a maximum
temperature, this module answers:

* :func:`conductor_temperature` -- what is the steady-state conductor
  temperature for a given current? (used inside the electro-thermal loop)
* :func:`ampacity` -- what is the current that just reaches
  :math:`T_{max}`? (used for the rating column of the results)
* :func:`heat_terms` -- what are each of the heat-balance terms at a given
  temperature? (used by the per-span diagnostic output)

The equations come straight from PPL-CH-001 CS-11 to CS-15 and
IEEE Std 738-2012; a short summary is in each function docstring.

The heat balance of a bare conductor in steady state is

.. math::

    I^2\,R(T_s) + q_s(T_s) = q_c(T_s, V_w, T_a, H_e) + q_r(T_s, T_a),

where :math:`I` is the current per sub-conductor, :math:`R(T_s)` the AC
resistance per metre, :math:`q_s` solar heat gain, :math:`q_c` convective
cooling and :math:`q_r` radiative cooling (all in W/m). The function
:func:`conductor_temperature` solves this for :math:`T_s` with Brent's
method.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import scipy.optimize

from pypowerlines.constants import STEFAN_BOLTZMAN
from pypowerlines.errors import ThermalBracketError
from pypowerlines.model import ConductorType, WeatherState
from pypowerlines.physics.lineparams import rac_per_m

__all__ = [
    "HeatTerms",
    "air_conductivity",
    "air_density",
    "air_viscosity",
    "ampacity",
    "conductor_temperature",
    "heat_terms",
    "standard_pressure_pa",
    "wind_angle_factor",
]


# ---------------------------------------------------------------------------
# Standard atmosphere and air properties (PPL-CH-001 CS-11, CS-28)
# ---------------------------------------------------------------------------


def standard_pressure_pa(elevation_m: float) -> float:
    r"""Atmospheric pressure at a given elevation, Pa.

    ISO 2533 standard atmosphere (PPL-CH-001 CS-28).

    Parameters
    ----------
    elevation_m : float

    Returns
    -------
    float
        Pressure, Pa.
    """
    h = max(elevation_m, 0.0)
    return float(101_325.0 * (1.0 - 2.25577e-5 * h) ** 5.25588)


def air_density(film_c: float, elevation_m: float = 0.0) -> float:
    r"""Air density at film temperature and elevation, kg/m³ (CS-11)."""
    he = max(elevation_m, 0.0)
    numerator = 1.293 - 1.525e-4 * he + 6.379e-9 * he * he
    return numerator / (1.0 + 0.00367 * film_c)


def air_viscosity(film_c: float) -> float:
    r"""Dynamic viscosity of air at film temperature, Pa·s (CS-11)."""
    tk = film_c + 273.0
    return float(1.458e-6 * tk**1.5 / (film_c + 383.4))


def air_conductivity(film_c: float) -> float:
    r"""Thermal conductivity of air at film temperature, W/(m·K) (CS-11)."""
    return 2.424e-2 + 7.477e-5 * film_c - 4.407e-9 * film_c * film_c


def wind_angle_factor(wind_angle_deg: float) -> float:
    r"""IEEE 738 wind-angle factor :math:`K_{angle}` (CS-14)."""
    phi = math.radians(wind_angle_deg)
    return 1.194 - math.cos(phi) + 0.194 * math.cos(2.0 * phi) + 0.368 * math.sin(2.0 * phi)


# Reasonable upper bound on conductor temperature during the Brent search
# (CS-15). Well above any realistic operating point but low enough to
# avoid losing precision in the T^4 radiative term.
_T_MAX_SEARCH_C: Final[float] = 500.0
"""Upper search bound for the heat-balance root, °C."""

_BRENT_TOL_K: Final[float] = 1e-2
"""Tolerance for the root finder, K (tighter than the outer coupling loop)."""

_MIN_BRACKET_LOW_C: Final[float] = -50.0
"""Lower bound of the initial Brent bracket, °C (far enough below any ambient)."""

_BRACKET_STEP_K: Final[float] = 5.0
"""How far the low end is lowered on each iteration when forcing a sign change."""


@dataclass(frozen=True, slots=True)
class HeatTerms:
    """Decomposition of the steady-state heat balance.

    All quantities are per metre of conductor (per phase). A positive
    value is a heat *gain* and a negative value a heat *loss*.

    Parameters
    ----------
    q_joule : float
        Joule (:math:`I^2 R`) heating, W/m.
    q_solar : float
        Solar heat gain, W/m.
    q_conv : float
        Convective heat loss, W/m (reported as a positive loss).
    q_rad : float
        Radiative heat loss, W/m (reported as a positive loss).

    Attributes
    ----------
    residual : float
        ``q_joule + q_solar - q_conv - q_rad``; 0 at the operating point.
    """

    q_joule: float
    q_solar: float
    q_conv: float
    q_rad: float

    @property
    def residual(self) -> float:
        """Heat-balance residual; zero at the steady-state temperature."""
        return self.q_joule + self.q_solar - self.q_conv - self.q_rad


# ---------------------------------------------------------------------------
# Individual heat-balance terms (CS-12, CS-13, CS-14)
# ---------------------------------------------------------------------------


def _solar_gain_wpm(conductor: ConductorType, weather: WeatherState) -> float:
    r"""Compute the solar heat gain per metre, W/m (CS-12).

    The irradiance passed in already includes the geometry factor
    (effective incidence) so the formula reduces to :math:`q_s = \alpha E D`.
    """
    return conductor.absorptivity * weather.irradiance_wm2 * conductor.diameter_m


def _radiative_loss_wpm(conductor: ConductorType, t_s_c: float, weather: WeatherState) -> float:
    r"""Radiative heat loss per metre, W/m.

    Stefan-Boltzmann form (CS-13):

    .. math::

        q_r = \pi D \sigma \epsilon (T_{s,K}^4 - T_{a,K}^4)

    Parameters
    ----------
    conductor : ConductorType
    t_s_c : float
        Conductor surface temperature, °C.
    weather : WeatherState

    Returns
    -------
    float
        Radiative loss per metre, W/m (positive).
    """
    t_s_k = t_s_c + 273.15
    t_a_k = weather.ambient_k
    return (
        math.pi
        * conductor.diameter_m
        * STEFAN_BOLTZMAN
        * conductor.emissivity
        * (t_s_k**4 - t_a_k**4)
    )


def _convective_loss_wpm(conductor: ConductorType, t_s_c: float, weather: WeatherState) -> float:
    r"""Convective heat loss per metre, W/m.

    Combined forced/natural convection (CS-14): takes the larger of the
    two forced-convection correlations and natural convection.

    Parameters
    ----------
    conductor : ConductorType
    t_s_c : float
        Conductor surface temperature, °C.
    weather : WeatherState

    Returns
    -------
    float
        Convective loss per metre, W/m (positive).
    """
    t_a = weather.ambient_c
    delta_t = t_s_c - t_a
    if delta_t <= 0.0:
        # Convective cooling only operates when the conductor is hotter
        # than the air; return zero to avoid negative (heating) values.
        return 0.0

    t_film = 0.5 * (t_s_c + t_a)
    mu_f = air_viscosity(t_film)
    k_f = air_conductivity(t_film)
    rho_f = air_density(t_film, weather.elevation_m)
    k_angle = wind_angle_factor(weather.wind_angle_deg)
    diameter = conductor.diameter_m
    v = max(weather.wind_ms, 0.0)

    # Forced convection (CS-14): two correlations, keep the larger.
    nre = diameter * rho_f * v / mu_f
    q_c1 = k_angle * (1.01 + 1.35 * nre**0.52) * k_f * delta_t
    q_c2 = k_angle * 0.754 * nre**0.6 * k_f * delta_t
    q_forced = max(q_c1, q_c2)

    # Natural convection (CS-14).
    q_natural = 3.645 * rho_f**0.5 * diameter**0.75 * delta_t**1.25

    return float(max(q_forced, q_natural))


# ---------------------------------------------------------------------------
# Heat balance
# ---------------------------------------------------------------------------


def heat_terms(
    conductor: ConductorType,
    t_s_c: float,
    i_per_sub_a: float,
    weather: WeatherState,
    frequency_hz: float = 50.0,
) -> HeatTerms:
    """Evaluate the four heat-balance terms at a given conductor temperature.

    Parameters
    ----------
    conductor : ConductorType
    t_s_c : float
        Conductor surface temperature, °C.
    i_per_sub_a : float
        Current per sub-conductor, A (= line current / ``sub_conductors``
        / ``circuits``).
    weather : WeatherState
    frequency_hz : float, default 50.0
        System frequency, Hz (for the skin-effect correction).

    Returns
    -------
    HeatTerms
        Each term in W/m. :attr:`HeatTerms.residual` is zero at the
        steady-state temperature.
    """
    r = rac_per_m(conductor, t_s_c, frequency_hz)
    q_joule = i_per_sub_a * i_per_sub_a * r
    q_solar = _solar_gain_wpm(conductor, weather)
    q_conv = _convective_loss_wpm(conductor, t_s_c, weather)
    q_rad = _radiative_loss_wpm(conductor, t_s_c, weather)
    return HeatTerms(q_joule=q_joule, q_solar=q_solar, q_conv=q_conv, q_rad=q_rad)


def conductor_temperature(  # noqa: PLR0913 -- one argument per IEEE 738 input
    conductor: ConductorType,
    current_a: float,
    weather: WeatherState,
    *,
    circuits: int = 1,
    frequency_hz: float = 50.0,
    span_id: str = "",
) -> float:
    r"""Steady-state conductor temperature at a given current, °C.

    Solves :math:`f(T_s) = I^2 R(T_s) + q_s - q_c(T_s) - q_r(T_s) = 0`
    for :math:`T_s` with Brent's method, bracketing between the ambient
    temperature and :data:`_T_MAX_SEARCH_C`.

    ``current_a`` is the whole-phase current; it is divided by
    ``conductor.sub_conductors`` and ``circuits`` to get the current per
    sub-conductor used in the heat balance.

    Parameters
    ----------
    conductor : ConductorType
    current_a : float
        Line (phase) current magnitude in the whole bundle, A.
    weather : WeatherState
    circuits : int, default 1
        Number of parallel circuits sharing the current.
    frequency_hz : float, default 50.0
    span_id : str, default ""
        Identifier used in the error raised if the root cannot be
        bracketed.

    Returns
    -------
    float
        Conductor temperature, °C.

    Raises
    ------
    ThermalBracketError
        If the heat balance does not change sign in the search bracket,
        meaning no physical steady-state temperature exists for those
        inputs.
    """
    i_per_sub = abs(current_a) / max(conductor.sub_conductors * circuits, 1)

    def residual(t_c: float) -> float:
        terms = heat_terms(conductor, t_c, i_per_sub, weather, frequency_hz)
        return terms.residual

    lo = weather.ambient_c
    # The ambient value can itself give a positive residual (solar gain
    # exceeds convective/radiative loss at zero delta-T): nudge the low
    # end down a little to force a sign change for very small currents.
    while residual(lo) > 0.0 and lo > _MIN_BRACKET_LOW_C:
        lo -= _BRACKET_STEP_K
    hi = _T_MAX_SEARCH_C
    f_lo = residual(lo)
    f_hi = residual(hi)
    if f_lo == 0.0:
        return lo
    if f_hi == 0.0:
        return hi
    if f_lo * f_hi > 0.0:
        raise ThermalBracketError(
            span_id=span_id,
            i_a=current_a,
            weather={
                "ambient_c": weather.ambient_c,
                "wind_ms": weather.wind_ms,
                "irradiance_wm2": weather.irradiance_wm2,
            },
        )
    return float(scipy.optimize.brentq(residual, lo, hi, xtol=_BRENT_TOL_K))


def ampacity(
    conductor: ConductorType,
    weather: WeatherState,
    *,
    t_max_c: float | None = None,
    circuits: int = 1,
    frequency_hz: float = 50.0,
) -> float:
    r"""Return the current at which the conductor just reaches :math:`T_{max}`.

    Closed form from PPL-CH-001 CS-15 at :math:`T_s = T_{max}`:

    .. math::

        I = \sqrt{\frac{q_c(T_{max}) + q_r(T_{max}) - q_s}{R_{ac}(T_{max})}}
                 \cdot n_{sub}

    The returned value is the whole-phase (bundle) current; multiplying by
    ``circuits`` gives the line rating.

    Parameters
    ----------
    conductor : ConductorType
    weather : WeatherState
    t_max_c : float, optional
        Maximum allowed conductor temperature, °C. Falls back to
        :attr:`ConductorType.t_max_c`.
    circuits : int, default 1
    frequency_hz : float, default 50.0

    Returns
    -------
    float
        Ampacity (whole-phase) per circuit, A. ``0.0`` if the cooling
        cannot remove even the solar gain (hot ambient, calm air, high
        irradiance).
    """
    t = t_max_c if t_max_c is not None else conductor.t_max_c
    q_conv = _convective_loss_wpm(conductor, t, weather)
    q_rad = _radiative_loss_wpm(conductor, t, weather)
    q_solar = _solar_gain_wpm(conductor, weather)
    numerator = q_conv + q_rad - q_solar
    if numerator <= 0.0:
        return 0.0
    r = rac_per_m(conductor, t, frequency_hz)
    i_per_sub = math.sqrt(numerator / r)
    return i_per_sub * conductor.sub_conductors
