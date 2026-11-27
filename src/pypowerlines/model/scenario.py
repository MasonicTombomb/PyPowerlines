"""Study-level objects: solver options, scenarios and the top-level Study.

A :class:`Study` is the single immutable object the solver works on. It
collects the validated network (:class:`~pypowerlines.model.Grid`), the
scenarios to solve and the numerical options.

Scenarios in v1 are single snapshots (no time series yet). Each one names
its own weather and injections, so a run can solve several weather cases
without re-loading the grid (PPL-REF-001 section 4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

from .components import Grid

__all__ = ["Scenario", "SolverOptions", "Study"]


_DEFAULT_PF_TOL: Final[float] = 1e-8
"""Default power-flow convergence tolerance, per unit (PPL-ALG-001 Table 2)."""

_DEFAULT_PF_MAX_ITER: Final[int] = 30
"""Default Newton-Raphson iteration limit."""

_DEFAULT_THERMAL_TOL_K: Final[float] = 0.1
"""Default outer-loop tolerance on span temperatures, K."""

_DEFAULT_THERMAL_MAX_ITER: Final[int] = 20
"""Default outer-loop iteration limit."""


@dataclass(frozen=True, slots=True)
class SolverOptions:
    """Numerical and physical options for a solver run.

    Defaults come from PPL-ALG-001 Table 2 and PPL-DATA-001 Table 2.

    Parameters
    ----------
    pf_tolerance_pu : float, default 1e-8
        Maximum absolute power mismatch, per unit, for NR convergence.
    pf_max_iter : int, default 30
        Newton-Raphson iteration limit.
    coupling : bool, default True
        When True, run the electro-thermal outer loop. When False, use the
        conductor temperature set by ``t_start_c`` throughout (reference
        "R at 20 °C" curve in PPL-REF-001).
    thermal_tolerance_k : float, default 0.1
        Convergence tolerance for the outer loop, K.
    thermal_max_iter : int, default 20
        Outer-loop iteration limit.
    relaxation : float, default 1.0
        Relaxation factor ``w`` in ``T <- T + w (T_new - T)``. Lower to
        damp oscillation (0 < w ≤ 1).
    thermal_model : str, default "ieee738_2012"
        Name of the thermal model. Only IEEE 738 is implemented in v1.
    t_start_c : float, default 20.0
        Initial conductor temperature for the outer loop, °C. The spec
        suggests ``ambient + 20 K``; using a plain 20 °C here is close
        enough and avoids a per-span start value in options.
    t_max_c : float | None, default None
        Override for the maximum allowed conductor temperature when
        computing ampacity, °C. ``None`` means use each conductor's
        ``t_max_c`` from the library.
    """

    pf_tolerance_pu: float = _DEFAULT_PF_TOL
    pf_max_iter: int = _DEFAULT_PF_MAX_ITER
    coupling: bool = True
    thermal_tolerance_k: float = _DEFAULT_THERMAL_TOL_K
    thermal_max_iter: int = _DEFAULT_THERMAL_MAX_ITER
    relaxation: float = 1.0
    thermal_model: str = "ieee738_2012"
    t_start_c: float = 20.0
    t_max_c: float | None = None


@dataclass(frozen=True, slots=True)
class Scenario:
    """One weather / load snapshot to solve.

    A scenario carries everything that varies between study runs on the
    same grid: weather per zone and the active-power / reactive-power
    injections at each bus. The grid itself does not change.

    Parameters
    ----------
    id : str
        Unique identifier of the scenario (used in output file names).
    name : str
        Human-readable name.
    ambient_c : float
        Scenario-wide base ambient temperature. Zone offsets are added on
        top to get the per-zone ambient.
    wind_ms : float
        Scenario-wide base wind speed. Zone multipliers are applied on top.
    irradiance_wm2 : float, default 0.0
        Solar irradiance applied to every zone.
    wind_angle_deg : float, default 90.0
        Angle of wind relative to conductor axis, degrees.
    rain_mmh : float, default 0.0
        Rainfall rate for corona losses.
    gen_p_mw : Mapping[str, float], optional
        Overrides for generator dispatch in this scenario,
        ``{generator_id: p_mw}``. Missing generators keep their grid value.
    load_p_mw, load_q_mvar : Mapping[str, float], optional
        Overrides for load injections in this scenario.
    """

    id: str
    name: str
    ambient_c: float
    wind_ms: float
    irradiance_wm2: float = 0.0
    wind_angle_deg: float = 90.0
    rain_mmh: float = 0.0
    gen_p_mw: dict[str, float] = field(default_factory=dict)
    load_p_mw: dict[str, float] = field(default_factory=dict)
    load_q_mvar: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Study:
    """Everything needed to run one or more snapshot solves.

    Parameters
    ----------
    id : str
        Study identifier.
    name : str
        Human-readable name.
    frequency_hz : float
        System frequency, Hz. Determines all reactances and susceptances.
    base_mva : float
        System MVA base used for per-unit conversion.
    grid : Grid
        The validated network.
    scenarios : tuple[Scenario, ...]
        Scenarios to solve (at least one).
    options : SolverOptions
        Solver options (same for every scenario in a study).
    """

    id: str
    name: str
    frequency_hz: float
    base_mva: float
    grid: Grid
    scenarios: tuple[Scenario, ...]
    options: SolverOptions = field(default_factory=SolverOptions)

    @property
    def omega(self) -> float:
        r"""Angular frequency :math:`\omega = 2\pi f`, in rad/s."""
        return 2.0 * math.pi * self.frequency_hz
