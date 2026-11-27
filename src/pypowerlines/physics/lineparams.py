r"""Overhead line parameters: resistance, reactance and susceptance.

All formulae are PPL-CH-001 CS-05 to CS-09. The functions are pure and
return per-metre values in SI; callers add the ``* length_m`` and divide
by circuits where needed.

A line may cross more than one weather zone. Each span owns its own
conductor temperature, so the line resistance is
:math:`\sum_s R_{ac}(T_s)\,\ell_s`. Reactance and susceptance depend on
geometry only, so they are summed by length regardless of temperature.
"""

from __future__ import annotations

import math
from typing import Final

from pypowerlines.constants import EPSILON_0, MU_0
from pypowerlines.model import ConductorType, TowerType

__all__ = [
    "bundle_gmr_m",
    "bundle_req_m",
    "line_pi_parameters",
    "phase_gmd_m",
    "rac_per_m",
    "rdc_per_m",
    "series_reactance_per_m",
    "shunt_susceptance_per_m",
]

_PHASES_PER_CIRCUIT: Final[int] = 3
"""Number of phases per three-phase circuit (positive-sequence model)."""

_TWIN_BUNDLE: Final[int] = 2
"""Sub-conductor count for a twin bundle (special-cased for its closed form)."""


# ---------------------------------------------------------------------------
# Resistance (CS-05, CS-06)
# ---------------------------------------------------------------------------


def rdc_per_m(conductor: ConductorType, t_c: float) -> float:
    r"""Temperature-corrected DC resistance per metre, Ω/m.

    Linear form from PPL-CH-001 CS-05:

    .. math::

        R(T) = R_{20}\,[1 + \alpha_{20}\,(T - 20)]

    Parameters
    ----------
    conductor : ConductorType
        The conductor whose ``r20_ohm_per_m`` and ``alpha_per_k`` are used.
    t_c : float
        Conductor temperature, °C.

    Returns
    -------
    float
        DC resistance per metre, Ω/m.
    """
    return conductor.r20_ohm_per_m * (1.0 + conductor.alpha_per_k * (t_c - 20.0))


def rac_per_m(conductor: ConductorType, t_c: float, frequency_hz: float = 50.0) -> float:
    r"""AC resistance per metre including skin effect, Ω/m.

    IEC 60287-1-1 form (PPL-CH-001 CS-06):

    .. math::

        x_s^2 = 8\pi f \cdot 10^{-7} k_s / R'_{dc}, \quad
        y_s = x_s^4 / (192 + 0.8\,x_s^4), \quad
        R_{ac} = R_{dc}(1 + y_s)

    Parameters
    ----------
    conductor : ConductorType
    t_c : float
        Conductor temperature, °C.
    frequency_hz : float, default 50.0
        System frequency, Hz.

    Returns
    -------
    float
        AC resistance per metre, Ω/m.

    Notes
    -----
    For stranded round conductors the construction factor :math:`k_s` is 1
    (CS-06). ACSR conductors with an odd number of aluminium layers can
    have an extra 1-5 % transformer effect; this v1 ignores it.
    """
    r_dc = rdc_per_m(conductor, t_c)
    xs2 = 8.0 * math.pi * frequency_hz * 1e-7 / r_dc
    xs4 = xs2 * xs2
    ys = xs4 / (192.0 + 0.8 * xs4)
    return r_dc * (1.0 + ys)


# ---------------------------------------------------------------------------
# Geometry: GMD and GMR (CS-07)
# ---------------------------------------------------------------------------


def phase_gmd_m(tower: TowerType) -> float:
    r"""Geometric mean distance between the three phase centres, m.

    .. math::

        D_{eq} = (D_{ab} D_{bc} D_{ca})^{1/3}

    Parameters
    ----------
    tower : TowerType
        Tower whose first three phase coordinates give the spacings.

    Returns
    -------
    float
        Equivalent phase spacing, metres.

    Raises
    ------
    ValueError
        If the tower has fewer than three phase positions.
    """
    phases = tower.phases_m
    if len(phases) < _PHASES_PER_CIRCUIT:
        raise ValueError(
            f"tower {tower.name!r} needs at least three phase positions to compute GMD",
        )
    (ax, ay), (bx, by), (cx, cy) = phases[0], phases[1], phases[2]
    d_ab = math.hypot(bx - ax, by - ay)
    d_bc = math.hypot(cx - bx, cy - by)
    d_ca = math.hypot(ax - cx, ay - cy)
    return (d_ab * d_bc * d_ca) ** (1.0 / 3.0)


def bundle_gmr_m(conductor: ConductorType) -> float:
    r"""Geometric mean radius of a phase conductor or bundle, m.

    PPL-CH-001 CS-07:

    * single conductor: :math:`\mathrm{GMR}_c = 0.7788\,r` (solid round
      assumption; more accurate stranded values are allowed via the
      library data but are not stored separately in v1).
    * bundle of :math:`n`: :math:`\mathrm{GMR}_b = (n \cdot \mathrm{GMR}_c \cdot R_b^{n-1})^{1/n}`
      where :math:`R_b = s / (2 \sin(\pi/n))`.

    Twin bundles use the closed form :math:`\sqrt{\mathrm{GMR}_c \cdot s}`.

    Parameters
    ----------
    conductor : ConductorType

    Returns
    -------
    float
        GMR of the phase (bundle) in metres.
    """
    radius = conductor.diameter_m / 2.0
    gmr_c = 0.7788 * radius
    n = conductor.sub_conductors
    if n <= 1:
        return gmr_c
    s = conductor.bundle_spacing_m
    if n == _TWIN_BUNDLE:
        return math.sqrt(gmr_c * s)
    bundle_radius = s / (2.0 * math.sin(math.pi / n))
    return (n * gmr_c * bundle_radius ** (n - 1)) ** (1.0 / n)


def bundle_req_m(conductor: ConductorType) -> float:
    r"""Equivalent radius of a phase bundle for capacitance, m.

    Same formula as :func:`bundle_gmr_m` but with the physical conductor
    radius :math:`r` in place of :math:`\mathrm{GMR}_c` (CS-07).

    Parameters
    ----------
    conductor : ConductorType

    Returns
    -------
    float
        Equivalent bundle radius for capacitance, metres.
    """
    radius = conductor.diameter_m / 2.0
    n = conductor.sub_conductors
    if n <= 1:
        return radius
    s = conductor.bundle_spacing_m
    if n == _TWIN_BUNDLE:
        return math.sqrt(radius * s)
    bundle_radius = s / (2.0 * math.sin(math.pi / n))
    return (n * radius * bundle_radius ** (n - 1)) ** (1.0 / n)


# ---------------------------------------------------------------------------
# Reactance and susceptance (CS-08, CS-09)
# ---------------------------------------------------------------------------


def series_reactance_per_m(
    conductor: ConductorType, tower: TowerType, frequency_hz: float = 50.0
) -> float:
    r"""Positive-sequence series reactance per metre, Ω/m.

    PPL-CH-001 CS-08:

    .. math::

        L = \frac{\mu_0}{2\pi} \ln(\mathrm{GMD} / \mathrm{GMR}_b), \quad X = 2\pi f L

    Parameters
    ----------
    conductor, tower : ConductorType, TowerType
    frequency_hz : float, default 50.0

    Returns
    -------
    float
        Reactance per metre, Ω/m.
    """
    gmd = phase_gmd_m(tower)
    gmr = bundle_gmr_m(conductor)
    inductance = (MU_0 / (2.0 * math.pi)) * math.log(gmd / gmr)
    return 2.0 * math.pi * frequency_hz * inductance


def shunt_susceptance_per_m(
    conductor: ConductorType, tower: TowerType, frequency_hz: float = 50.0
) -> float:
    r"""Positive-sequence shunt susceptance per metre, S/m.

    PPL-CH-001 CS-09:

    .. math::

        C = \frac{2\pi\varepsilon_0}{\ln(\mathrm{GMD} / r_{eq})}, \quad B = 2\pi f C

    Parameters
    ----------
    conductor, tower : ConductorType, TowerType
    frequency_hz : float, default 50.0

    Returns
    -------
    float
        Susceptance per metre, S/m (positive for a capacitive shunt).
    """
    gmd = phase_gmd_m(tower)
    req = bundle_req_m(conductor)
    capacitance = 2.0 * math.pi * EPSILON_0 / math.log(gmd / req)
    return 2.0 * math.pi * frequency_hz * capacitance


# ---------------------------------------------------------------------------
# Line pi model assembly
# ---------------------------------------------------------------------------


def line_pi_parameters(
    spans: tuple,
    circuits: int,
    frequency_hz: float = 50.0,
    span_temperatures_c: tuple[float, ...] | None = None,
) -> tuple[complex, complex]:
    r"""Series impedance and total shunt admittance of a multi-span line.

    Builds the lumped nominal :math:`\pi` model summed over spans:

    * series impedance :math:`z_\text{series} = \sum_s (R_s + j X_s) / n_c`
      with :math:`R_s = R_{ac}(T_s) \ell_s` and :math:`X_s = X \ell_s`;
    * total shunt admittance :math:`y_\text{shunt} = j B_s \ell_s n_c` per
      span (half goes to each end of the line in the Y-bus assembly).

    Parameters
    ----------
    spans : tuple[Span, ...]
        Spans of the line, in order.
    circuits : int
        Number of parallel circuits on the same route.
    frequency_hz : float, default 50.0
    span_temperatures_c : tuple[float, ...], optional
        Temperature of each span in °C. If omitted, 20 °C is used for
        every span (useful to reproduce the "R at 20 °C" curve).

    Returns
    -------
    (complex, complex)
        ``(z_series_ohm, y_shunt_siemens)``: total series impedance (Ω)
        and total shunt admittance (S) referred to the ends of the line.

    Raises
    ------
    ValueError
        If ``span_temperatures_c`` is given but its length does not match
        ``spans``.
    """
    if span_temperatures_c is None:
        span_temperatures_c = (20.0,) * len(spans)
    if len(span_temperatures_c) != len(spans):
        raise ValueError(
            f"got {len(span_temperatures_c)} span temperatures for {len(spans)} spans",
        )

    z_series = 0j
    y_shunt = 0j
    for span, t_c in zip(spans, span_temperatures_c, strict=True):
        r = rac_per_m(span.conductor, t_c, frequency_hz) * span.length_m
        x = series_reactance_per_m(span.conductor, span.tower, frequency_hz) * span.length_m
        b = shunt_susceptance_per_m(span.conductor, span.tower, frequency_hz) * span.length_m
        z_series += complex(r, x)
        y_shunt += complex(0.0, b)

    return z_series / circuits, y_shunt * circuits
