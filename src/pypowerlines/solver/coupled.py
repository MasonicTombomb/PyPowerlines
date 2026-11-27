"""Coupled electro-thermal snapshot solver.

Orchestrates one scenario from study inputs to :class:`SnapshotResult`.
The flow (PPL-ALG-001 section 1, PPL-SDS-001 section 5.6):

1. Build the specified injection vectors from the grid, scenario and
   bus-type data.
2. Guess an initial conductor temperature per line (default: ambient
   + 20 K, following PPL-ALG-001 Table 2).
3. Loop:

   a. Rebuild line resistances at the current temperatures.
   b. Solve the AC power flow.
   c. Extract the current magnitude in each line.
   d. For each line, solve the heat balance in each zone it crosses.
   e. Relax and check the max temperature change; if below tolerance,
      converged.

4. Compute branch flows, losses, ratings and bus results; wrap into a
   :class:`SnapshotResult`.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from pypowerlines._log import get_logger
from pypowerlines.environment import resolve_weather
from pypowerlines.errors import CouplingNotConverged, NumericalError
from pypowerlines.model import (
    BranchResult,
    BusResult,
    ConductorResult,
    Line,
    Scenario,
    SnapshotResult,
    Study,
    Transformer,
    TransformerResult,
)
from pypowerlines.physics import thermal
from pypowerlines.physics.lineparams import line_pi_parameters

from .network import Branch, branch_current_amperes, build_branches, update_line_resistance
from .powerflow import PowerFlowSolution, build_ybus, solve_powerflow

__all__ = ["solve_scenario"]


_log = get_logger(__name__)


_V_PU_LOW: Final[float] = 0.95
"""Lower edge of the ±5 % acceptable voltage band (PPL-SDS-001)."""

_V_PU_HIGH: Final[float] = 1.05
"""Upper edge of the ±5 % acceptable voltage band."""


# ---------------------------------------------------------------------------
# Scenario injections
# ---------------------------------------------------------------------------


def _build_injections(
    study: Study, scenario: Scenario
) -> tuple[np.ndarray, np.ndarray, list, np.ndarray]:
    """Return ``(p_spec_pu, q_spec_pu, bus_types, v_set_pu)``.

    * ``p_spec_pu[i]`` = sum of generator P at bus ``i`` minus sum of
      load P at bus ``i``, in per unit on ``study.base_mva``.
    * ``q_spec_pu[i]`` = same for Q; ignored at PV and slack buses.
    * ``bus_types[i]`` = from the grid.
    * ``v_set_pu[i]`` = bus ``v_set_pu`` for PV and slack, 1.0 elsewhere
      (fallback that is never used by NR for PQ buses).
    """
    grid = study.grid
    n = len(grid.buses)
    bus_idx = grid.bus_index()
    p = np.zeros(n)
    q = np.zeros(n)

    for gen in grid.generators:
        idx = bus_idx[gen.bus.id]
        p[idx] += scenario.gen_p_mw.get(gen.id, gen.p_mw)
        # PV/slack buses hold their voltage, so q here is a free variable
        # and we leave it at 0 (overwritten inside NR).

    for load in grid.loads:
        idx = bus_idx[load.bus.id]
        p[idx] -= scenario.load_p_mw.get(load.id, load.p_mw)
        q[idx] -= scenario.load_q_mvar.get(load.id, load.q_mvar)

    p_pu = p / study.base_mva
    q_pu = q / study.base_mva

    bus_types = [bus.type for bus in grid.buses]
    v_set = np.array([bus.v_set_pu for bus in grid.buses], dtype=float)
    return p_pu, q_pu, bus_types, v_set


# ---------------------------------------------------------------------------
# Branch currents
# ---------------------------------------------------------------------------


def _branch_from_current_pu(branch: Branch, v_complex: np.ndarray) -> complex:
    r"""Return the current from the "from" bus into the branch, per unit.

    From the admittance representation with HV-side tap :math:`t`:

    .. math::

        I_f = (V_f / t^2) (y + y_{sh}/2) - (V_t / t) y

    For a line :math:`t = 1`.
    """
    vf = v_complex[branch.from_idx] / branch.tap
    vt = v_complex[branch.to_idx]
    return (vf - vt) * branch.y_series_pu + vf * branch.y_shunt_half_pu


def _branch_to_current_pu(branch: Branch, v_complex: np.ndarray) -> complex:
    r"""Return the current from the "to" bus into the branch, per unit."""
    vf = v_complex[branch.from_idx] / branch.tap
    vt = v_complex[branch.to_idx]
    return (vt - vf) * branch.y_series_pu + vt * branch.y_shunt_half_pu


# ---------------------------------------------------------------------------
# Thermal update of one line
# ---------------------------------------------------------------------------


def _line_zones(line: Line) -> dict[str, tuple]:
    """Group ``line.spans`` by weather zone id.

    Returns
    -------
    dict[str, tuple[Span, ...]]
        Mapping zone id → the spans in that zone.
    """
    out: dict[str, list] = {}
    for span in line.spans:
        out.setdefault(span.zone.id, []).append(span)
    return {k: tuple(v) for k, v in out.items()}


def _solve_line_temperature(
    line: Line,
    current_a: float,
    scenario: Scenario,
    frequency_hz: float,
) -> tuple[float, dict[str, tuple[float, thermal.HeatTerms, float]]]:
    """Solve the heat balance for every zone the line crosses.

    In v1 we use one representative temperature per line in the resistance
    update. The value returned here is the length-weighted average of the
    per-zone temperatures, which matches the PPL-REF-001 assumption of
    "one temperature per line" (section 7).

    Parameters
    ----------
    line : Line
    current_a : float
        Line (phase) current magnitude in A, whole bundle, all circuits.
    scenario : Scenario
    frequency_hz : float

    Returns
    -------
    (float, dict[str, (T_c, HeatTerms, ampacity_a)])
        Line-level temperature and per-zone details for reporting.
    """
    zones = _line_zones(line)
    details: dict[str, tuple[float, thermal.HeatTerms, float]] = {}
    total_len = sum(s.length_m for s in line.spans)
    weighted_t = 0.0

    # Divide current by circuits so each conductor carries its share.
    i_per_circuit = current_a / max(line.circuits, 1)

    for zone_id, spans in zones.items():
        zone_len = sum(s.length_m for s in spans)
        representative = spans[0]
        weather = resolve_weather(scenario, representative.zone, representative)
        t_c = thermal.conductor_temperature(
            representative.conductor,
            i_per_circuit,
            weather,
            circuits=1,
            frequency_hz=frequency_hz,
            span_id=f"{line.id}@{zone_id}",
        )
        i_per_sub = i_per_circuit / representative.conductor.sub_conductors
        terms = thermal.heat_terms(
            representative.conductor,
            t_c,
            i_per_sub,
            weather,
            frequency_hz,
        )
        amp_a = thermal.ampacity(
            representative.conductor,
            weather,
            circuits=1,
            frequency_hz=frequency_hz,
        )
        details[zone_id] = (t_c, terms, amp_a)
        weighted_t += t_c * (zone_len / total_len if total_len > 0 else 1.0)

    return weighted_t, details


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def solve_scenario(
    study: Study,
    scenario: Scenario,
    *,
    warm_start: PowerFlowSolution | None = None,
) -> SnapshotResult:
    """Solve one scenario and return its complete result record.

    Parameters
    ----------
    study : Study
    scenario : Scenario
    warm_start : PowerFlowSolution, optional
        Previous solution to seed the NR starting voltages.

    Returns
    -------
    SnapshotResult
    """
    options = study.options
    p_pu, q_pu, bus_types, v_set_pu = _build_injections(study, scenario)

    # Starting temperatures: use a single global value per PPL-ALG-001
    # (ambient + 20 K). The dict is empty for the first build so that
    # build_branches uses 20 °C, then overwritten after the first solve.
    line_temperatures: dict[str, float] = {}

    branches = build_branches(study, line_temperatures)
    v_mag_start = warm_start.v_mag if warm_start is not None else None
    v_ang_start = warm_start.v_ang if warm_start is not None else None

    max_dt = float("inf")
    sol: PowerFlowSolution | None = None
    pass_count = 0
    warnings: list[str] = []

    while True:
        pass_count += 1
        try:
            sol = solve_powerflow(
                study,
                branches,
                p_pu,
                q_pu,
                tuple(bus_types),
                v_set_pu,
                v_start=v_mag_start,
                ang_start=v_ang_start,
            )
        except NumericalError:
            raise
        v_mag_start = sol.v_mag
        v_ang_start = sol.v_ang

        if not options.coupling:
            max_dt = 0.0
            break

        v_complex = sol.v_complex
        new_temps: dict[str, float] = {}
        for br in branches:
            if br.kind != "line":
                continue
            assert isinstance(br.model_ref, Line)
            i_pu = abs(_branch_from_current_pu(br, v_complex))
            i_a = branch_current_amperes(br, i_pu, study.base_mva)
            t_new, _ = _solve_line_temperature(br.model_ref, i_a, scenario, study.frequency_hz)
            t_old = line_temperatures.get(br.model_ref.id, options.t_start_c)
            relaxed = t_old + options.relaxation * (t_new - t_old)
            new_temps[br.model_ref.id] = relaxed

        max_dt = max(
            (abs(new_temps[k] - line_temperatures.get(k, options.t_start_c)) for k in new_temps),
            default=0.0,
        )

        line_temperatures = new_temps
        # Update resistances in place (reactance and shunt unchanged).
        for br in branches:
            if br.kind == "line":
                update_line_resistance(br, line_temperatures[br.branch_id], study)

        if max_dt < options.thermal_tolerance_k:
            break
        if pass_count >= options.thermal_max_iter:
            raise CouplingNotConverged(passes=pass_count, max_delta_t_k=max_dt)

    assert sol is not None
    return _package_result(study, scenario, branches, sol, pass_count, max_dt, warnings)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _package_result(  # noqa: PLR0913, PLR0917, PLR0915 -- single aggregation step
    study: Study,
    scenario: Scenario,
    branches: list[Branch],
    sol: PowerFlowSolution,
    pass_count: int,
    max_dt_k: float,
    warnings: list[str],
) -> SnapshotResult:
    """Build a :class:`SnapshotResult` from the converged power flow."""
    grid = study.grid
    base_mva = study.base_mva
    v = sol.v_complex

    # Bus-level results (injected P and Q are what the network sees from
    # the bus, so slack injection is also reported).
    s_calc = v * np.conj(_ybus_times_v(branches, v, len(grid.buses)))
    bus_results: list[BusResult] = []
    for i, bus in enumerate(grid.buses):
        bus_results.append(
            BusResult(
                bus_id=bus.id,
                v_pu=float(abs(v[i])),
                angle_deg=float(math.degrees(np.angle(v[i]))),
                p_inj_mw=float(s_calc[i].real) * base_mva,
                q_inj_mvar=float(s_calc[i].imag) * base_mva,
            )
        )
        v_pu = abs(v[i])
        if v_pu < _V_PU_LOW or v_pu > _V_PU_HIGH:
            warnings.append(f"bus {bus.id} voltage {v_pu:.3f} pu outside ±5% band")

    # Branch results
    branch_results: list[BranchResult] = []
    transformer_results: list[TransformerResult] = []
    total_loss_mw = 0.0
    total_loss_fixed_r_mw = 0.0

    # For the fixed-R comparison column: compute each line's loss as if R
    # were at 20 °C using the converged currents.
    for br in branches:
        s_from = v[br.from_idx] * np.conj(_branch_from_current_pu(br, v))
        s_to = v[br.to_idx] * np.conj(_branch_to_current_pu(br, v))
        p_from_mw = float(s_from.real) * base_mva
        q_from_mvar = float(s_from.imag) * base_mva
        p_to_mw = float(s_to.real) * base_mva
        q_to_mvar = float(s_to.imag) * base_mva
        loss_mw = p_from_mw + p_to_mw
        total_loss_mw += loss_mw

        i_from_pu = abs(_branch_from_current_pu(br, v))
        # For a pi-model with two circuits lumped into one admittance, the
        # reported |I| already includes both circuits; divide by circuits
        # to get per-circuit, matching PPL-REF-001 Table 6 "I per circuit".
        circuits = (
            br.model_ref.circuits
            if isinstance(br.model_ref, Line)
            else max(getattr(br.model_ref, "count", 1), 1)
        )
        i_a_total = branch_current_amperes(br, i_from_pu, base_mva)
        i_a_per_circuit = i_a_total / max(circuits, 1)

        conductors: tuple[ConductorResult, ...] = ()
        loading_pct = float("nan")
        if br.kind == "line" and isinstance(br.model_ref, Line):
            line = br.model_ref
            _, details = _solve_line_temperature(line, i_a_total, scenario, study.frequency_hz)
            cond_list = []
            amp_a = float("inf")
            for zone_id, (t_c, terms, zone_amp) in details.items():
                overload = i_a_per_circuit > zone_amp
                cond_list.append(
                    ConductorResult(
                        line_id=line.id,
                        zone_id=zone_id,
                        t_c=t_c,
                        ampacity_a=zone_amp,
                        q_joule_wpm=terms.q_joule,
                        q_solar_wpm=terms.q_solar,
                        q_conv_wpm=terms.q_conv,
                        q_rad_wpm=terms.q_rad,
                        overload=overload,
                    )
                )
                amp_a = min(amp_a, zone_amp)
                if overload:
                    warnings.append(
                        f"line {line.id} zone {zone_id}: "
                        f"{i_a_per_circuit:.0f} A > ampacity {zone_amp:.0f} A"
                    )
            conductors = tuple(cond_list)
            if amp_a > 0 and math.isfinite(amp_a):
                loading_pct = 100.0 * i_a_per_circuit / amp_a

            # Fixed-R comparison: compute |I|^2 R at 20 °C.
            z20, _ = line_pi_parameters(line.spans, line.circuits, study.frequency_hz, None)
            r20_ohm = z20.real
            # Three-phase I^2 R loss, line current = i_a_total.
            # The branch currents above are per phase at the from end; a
            # three-phase line loses 3 I^2 R per side, which matches the
            # pi-model loss when V_from ≈ V_to.
            loss20 = 3.0 * i_a_per_circuit * i_a_per_circuit * r20_ohm * circuits
            total_loss_fixed_r_mw += loss20 * 1e-6

        elif br.kind == "transformer" and isinstance(br.model_ref, Transformer):
            tx = br.model_ref
            s_mva = float(abs(s_from)) * base_mva
            # Rating of the bank
            rating = tx.type.rating_mva * tx.count
            if rating > 0:
                loading_pct = 100.0 * s_mva / rating
            v_hv_pu = abs(v[br.from_idx])
            p0 = tx.type.p0_kw * tx.count * v_hv_pu * v_hv_pu
            s_per_unit = s_mva / max(tx.count, 1)
            pk = tx.type.pk_kw * tx.count * (s_per_unit / tx.type.rating_mva) ** 2
            transformer_results.append(
                TransformerResult(
                    transformer_id=tx.id,
                    s_mva=s_mva,
                    p0_kw=p0,
                    pk_kw=pk,
                    loss_mw=(p0 + pk) * 1e-3,
                )
            )
            # Transformer loss at fixed-R has no coupling dependence.
            total_loss_fixed_r_mw += (p0 + pk) * 1e-3

        branch_results.append(
            BranchResult(
                branch_id=br.branch_id,
                kind=br.kind,
                from_bus=grid.buses[br.from_idx].id,
                to_bus=grid.buses[br.to_idx].id,
                p_from_mw=p_from_mw,
                q_from_mvar=q_from_mvar,
                p_to_mw=p_to_mw,
                q_to_mvar=q_to_mvar,
                i_a=i_a_per_circuit,
                loss_mw=loss_mw,
                loading_pct=loading_pct,
                conductors=conductors,
            )
        )

    return SnapshotResult(
        scenario_id=scenario.id,
        converged=True,
        nr_iterations=sol.iterations,
        coupling_passes=pass_count,
        max_mismatch_pu=sol.max_mismatch_pu,
        max_delta_t_k=max_dt_k,
        buses=tuple(bus_results),
        branches=tuple(branch_results),
        transformers=tuple(transformer_results),
        total_loss_mw=total_loss_mw,
        total_loss_fixed_r_mw=total_loss_fixed_r_mw,
        warnings=tuple(warnings),
    )


def _ybus_times_v(branches: list[Branch], v: np.ndarray, n: int) -> np.ndarray:
    """Compute ``Y @ v`` without rebuilding Y (helper for packaging)."""
    y = build_ybus(n, branches)
    return y @ v
