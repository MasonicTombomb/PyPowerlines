"""Branch representation used by the power flow and Y-bus assembly.

The solver works with a flat list of :class:`Branch` entries rather than
directly with :class:`~pypowerlines.model.Line` and
:class:`~pypowerlines.model.Transformer`. This keeps the Y-bus
assembly, admittance updates and branch-current extraction all in one
compact form.

Each branch carries its series admittance :math:`y = 1/z`, half its shunt
admittance :math:`y_{sh}/2` and the HV-side tap ratio :math:`t`. For a
line :math:`t = 1`; for a transformer :math:`t` comes from
:func:`~pypowerlines.physics.transformer.tap_ratio`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pypowerlines.model import Grid, Line, Study, Transformer
from pypowerlines.physics import lineparams
from pypowerlines.physics import transformer as xfmr_physics

__all__ = ["Branch", "build_branches", "update_line_resistance"]


BranchKind = Literal["line", "transformer"]


@dataclass(slots=True)
class Branch:
    """One admittance-level branch of the network.

    Attributes
    ----------
    branch_id : str
    kind : {"line", "transformer"}
    from_idx, to_idx : int
        Row indices into the Y-bus of the "from" and "to" ends.
    y_series_pu : complex
        Series admittance :math:`1/z`, per unit.
    y_shunt_half_pu : complex
        One half of the line charging admittance, per unit (added to each
        diagonal). Zero for transformers in v1.
    tap : float
        Off-nominal HV-side tap ratio. 1 for lines.
    model_ref : Line | Transformer
        Original model object; held for post-solve reporting.
    z_series_ohm : complex | None
        Original series impedance in physical ohms (lines only). Kept so
        the resistance part can be updated inside the electro-thermal
        loop without rebuilding the whole line.
    from_kv : float
        Nominal kV at the "from" bus (used to convert currents from pu to
        amperes).
    length_m : float
        Total length (metres); 0 for transformers.
    """

    branch_id: str
    kind: BranchKind
    from_idx: int
    to_idx: int
    y_series_pu: complex
    y_shunt_half_pu: complex
    tap: float
    model_ref: Line | Transformer
    z_series_ohm: complex | None
    from_kv: float
    length_m: float


def _z_base_ohm(kv: float, base_mva: float) -> float:
    """Return the base impedance for a voltage level, Ω (CS-02)."""
    return (kv * 1e3) ** 2 / (base_mva * 1e6)


def _i_base_a(kv: float, base_mva: float) -> float:
    """Return the base current for a voltage level, A (CS-02)."""
    return base_mva * 1e6 / (math.sqrt(3.0) * kv * 1e3)


def build_branches(
    study: Study, span_temperatures_c: dict[str, float] | None = None
) -> list[Branch]:
    """Build the flat branch list from the study.

    Called once per outer-loop pass: the branch list is rebuilt with
    the updated span temperatures, but transformer branches are
    unchanged between passes.

    Parameters
    ----------
    study : Study
    span_temperatures_c : dict[str, float] | None
        Mapping ``{line_id: {zone_id: T_c}}`` flattened as
        ``f"{line_id}@{zone_id}"`` is also accepted; in v1 we use a flat
        ``{line_id: T_c}`` giving one temperature per line. ``None`` means
        20 °C everywhere (the fixed-R reference).

    Returns
    -------
    list[Branch]
    """
    grid: Grid = study.grid
    bus_idx = grid.bus_index()
    branches: list[Branch] = []

    span_temps = span_temperatures_c or {}

    for line in grid.lines:
        t_line = span_temps.get(line.id, 20.0)
        temps = (t_line,) * len(line.spans)
        z_ohm, y_shunt_siemens = lineparams.line_pi_parameters(
            line.spans, line.circuits, study.frequency_hz, temps
        )
        kv = line.from_bus.kv
        z_base = _z_base_ohm(kv, study.base_mva)
        z_pu = z_ohm / z_base
        y_shunt_pu = complex(0.0, y_shunt_siemens.imag) * z_base
        y_series_pu = 1.0 / z_pu
        branches.append(
            Branch(
                branch_id=line.id,
                kind="line",
                from_idx=bus_idx[line.from_bus.id],
                to_idx=bus_idx[line.to_bus.id],
                y_series_pu=y_series_pu,
                y_shunt_half_pu=y_shunt_pu / 2.0,
                tap=1.0,
                model_ref=line,
                z_series_ohm=z_ohm,
                from_kv=kv,
                length_m=line.length_m,
            )
        )

    for tx in grid.transformers:
        z_pu_per_unit = xfmr_physics.series_impedance_pu(tx.type, study.base_mva)
        # Parallel count: z divides, y multiplies.
        z_pu = z_pu_per_unit / max(tx.count, 1)
        y_series_pu = 1.0 / z_pu
        tap = xfmr_physics.tap_ratio(tx.type, tx.tap_pos)
        branches.append(
            Branch(
                branch_id=tx.id,
                kind="transformer",
                from_idx=bus_idx[tx.hv_bus.id],
                to_idx=bus_idx[tx.lv_bus.id],
                y_series_pu=y_series_pu,
                y_shunt_half_pu=0j,
                tap=tap,
                model_ref=tx,
                z_series_ohm=None,
                from_kv=tx.hv_bus.kv,
                length_m=0.0,
            )
        )

    return branches


def update_line_resistance(
    branch: Branch,
    new_temperature_c: float,
    study: Study,
) -> None:
    """Update a line branch's series admittance with a new conductor temperature.

    The reactance and shunt susceptance are unchanged. Only the real part
    of :math:`z` moves, so this is a cheap in-place update inside the
    electro-thermal loop (PPL-ALG-001 section 2).

    Parameters
    ----------
    branch : Branch
        Must have ``kind == "line"``.
    new_temperature_c : float
    study : Study
    """
    if branch.kind != "line" or not isinstance(branch.model_ref, Line):
        raise ValueError(
            f"update_line_resistance called on branch {branch.branch_id!r} "
            f"of kind {branch.kind!r}",
        )
    line = branch.model_ref
    temps = (new_temperature_c,) * len(line.spans)
    z_ohm, _ = lineparams.line_pi_parameters(
        line.spans, line.circuits, study.frequency_hz, temps
    )
    z_base = _z_base_ohm(branch.from_kv, study.base_mva)
    branch.z_series_ohm = z_ohm
    branch.y_series_pu = 1.0 / (z_ohm / z_base)


def branch_current_amperes(
    branch: Branch, i_pu_magnitude: float, base_mva: float
) -> float:
    """Convert a per-unit current magnitude on the "from" side to amperes.

    Parameters
    ----------
    branch : Branch
    i_pu_magnitude : float
        Current magnitude in per unit at the from-bus voltage level.
    base_mva : float

    Returns
    -------
    float
        Current in amperes (line/phase, all circuits).
    """
    return i_pu_magnitude * _i_base_a(branch.from_kv, base_mva)
