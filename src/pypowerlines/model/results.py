"""Result data classes returned by the solvers.

A :class:`SnapshotResult` is everything the report writer needs to turn
one solved scenario into CSV rows and a JSON summary (PPL-SDS-001
section 5.4, Figure 5). Everything is in SI inside the simulator;
:mod:`pypowerlines.report` is the only module that converts to engineering
units (MW, kV, °C, A) for the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "BranchResult",
    "BusResult",
    "ConductorResult",
    "SnapshotResult",
    "TransformerResult",
]


@dataclass(frozen=True, slots=True)
class BusResult:
    """Power-flow solution at one bus.

    Parameters
    ----------
    bus_id : str
    v_pu : float
        Voltage magnitude, per unit.
    angle_deg : float
        Voltage angle, degrees (slack = 0).
    p_inj_mw, q_inj_mvar : float
        Net active / reactive power injected at the bus (generation minus
        load), MW / Mvar. Positive flows out of the bus into the network.
    """

    bus_id: str
    v_pu: float
    angle_deg: float
    p_inj_mw: float
    q_inj_mvar: float


@dataclass(frozen=True, slots=True)
class ConductorResult:
    """Thermal state of a line segment grouped by uniform weather.

    In v1 a line's spans are grouped by weather zone so that one
    temperature is reported per (line, zone) pair.

    Parameters
    ----------
    line_id : str
    zone_id : str
    t_c : float
        Converged conductor temperature, °C.
    ampacity_a : float
        Maximum current at the configured ``t_max_c``, whole bundle per
        circuit, A.
    q_joule_wpm, q_solar_wpm, q_conv_wpm, q_rad_wpm : float
        Decomposition of the heat balance at ``t_c``, W/m.
    overload : bool
        True when the actual current exceeds ``ampacity_a``.
    """

    line_id: str
    zone_id: str
    t_c: float
    ampacity_a: float
    q_joule_wpm: float
    q_solar_wpm: float
    q_conv_wpm: float
    q_rad_wpm: float
    overload: bool


@dataclass(frozen=True, slots=True)
class BranchResult:
    """Solved flows on one line (all its circuits combined).

    Parameters
    ----------
    branch_id : str
    kind : {"line", "transformer"}
    from_bus, to_bus : str
    p_from_mw, q_from_mvar, p_to_mw, q_to_mvar : float
        Three-phase power at each end, MW / Mvar.
    i_a : float
        Line current magnitude per circuit at the "from" end, A.
    loss_mw : float
        Active-power loss, MW.
    loading_pct : float
        ``100 * |i_a| / ampacity_a`` for lines; ``100 * S / rating`` for
        transformers. ``NaN`` when the rating is zero.
    conductors : tuple[ConductorResult, ...]
        Per-zone conductor results for a line (empty for transformers).
    """

    branch_id: str
    kind: str
    from_bus: str
    to_bus: str
    p_from_mw: float
    q_from_mvar: float
    p_to_mw: float
    q_to_mvar: float
    i_a: float
    loss_mw: float
    loading_pct: float
    conductors: tuple[ConductorResult, ...] = ()


@dataclass(frozen=True, slots=True)
class TransformerResult:
    """Solved loading and losses of a transformer bank.

    Parameters
    ----------
    transformer_id : str
    s_mva : float
        Apparent power through the bank, MVA.
    p0_kw : float
        Total no-load (iron) loss, kW.
    pk_kw : float
        Total load (copper) loss, kW.
    loss_mw : float
        Sum of the two, MW.
    """

    transformer_id: str
    s_mva: float
    p0_kw: float
    pk_kw: float
    loss_mw: float


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    """Everything one scenario solved produced.

    Parameters
    ----------
    scenario_id : str
    converged : bool
        True when both the power flow and (optionally) the coupling loop
        converged.
    nr_iterations : int
        Newton-Raphson iterations taken on the final pass.
    coupling_passes : int
        Outer-loop passes taken (1 means coupling was disabled).
    max_mismatch_pu : float
        Final NR mismatch, per unit.
    max_delta_t_k : float
        Largest temperature change on the last coupling pass, K.
    buses : tuple[BusResult, ...]
    branches : tuple[BranchResult, ...]
    transformers : tuple[TransformerResult, ...]
    total_loss_mw : float
        Sum of all branch and transformer losses, MW.
    total_loss_fixed_r_mw : float
        Same total recomputed with ``R`` evaluated at ``t_start_c`` (used
        for the "R at 20 °C" comparison column, PPL-REF-001 section 5).
        ``NaN`` when coupling is off.
    warnings : tuple[str, ...]
        Human-readable warnings (voltage band exceeded, overload, etc.).
    """

    scenario_id: str
    converged: bool
    nr_iterations: int
    coupling_passes: int
    max_mismatch_pu: float
    max_delta_t_k: float
    buses: tuple[BusResult, ...]
    branches: tuple[BranchResult, ...]
    transformers: tuple[TransformerResult, ...]
    total_loss_mw: float
    total_loss_fixed_r_mw: float = float("nan")
    warnings: tuple[str, ...] = field(default_factory=tuple)
