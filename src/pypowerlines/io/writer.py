"""CSV / JSON writers for solver results.

Each :class:`~pypowerlines.solver.SnapshotResult` produces four tables
plus one JSON summary, following PPL-DATA-001 Table 10. In v1 the
timestamp column of each table holds the scenario id (one row per
scenario id).
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pypowerlines.model import SnapshotResult

__all__ = ["write_results"]


_FIELDNAMES_BUSES: tuple[str, ...] = (
    "scenario",
    "bus",
    "v_pu",
    "angle_deg",
    "p_inj_mw",
    "q_inj_mvar",
)
_FIELDNAMES_BRANCHES: tuple[str, ...] = (
    "scenario",
    "branch",
    "kind",
    "from_bus",
    "to_bus",
    "p_from_mw",
    "q_from_mvar",
    "p_to_mw",
    "q_to_mvar",
    "i_a",
    "loss_mw",
    "loading_pct",
)
_FIELDNAMES_CONDUCTORS: tuple[str, ...] = (
    "scenario",
    "line",
    "zone",
    "t_c",
    "ampacity_a",
    "q_joule_wpm",
    "q_solar_wpm",
    "q_conv_wpm",
    "q_rad_wpm",
    "overload",
)
_FIELDNAMES_TRANSFORMERS: tuple[str, ...] = (
    "scenario",
    "transformer",
    "s_mva",
    "p0_kw",
    "pk_kw",
    "loss_mw",
)


def _write_csv(path: Path, fieldnames: Sequence[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_results(results: Sequence[SnapshotResult], outdir: str | Path) -> None:
    """Write buses.csv, branches.csv, conductors.csv, transformers.csv and summary.json.

    Parameters
    ----------
    results : Sequence[SnapshotResult]
        One per scenario.
    outdir : str or pathlib.Path
        Target directory; created if missing.
    """
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    buses_rows: list[dict[str, Any]] = []
    branches_rows: list[dict[str, Any]] = []
    conductors_rows: list[dict[str, Any]] = []
    transformers_rows: list[dict[str, Any]] = []

    for r in results:
        for b in r.buses:
            buses_rows.append(
                {
                    "scenario": r.scenario_id,
                    "bus": b.bus_id,
                    "v_pu": _round(b.v_pu, 6),
                    "angle_deg": _round(b.angle_deg, 4),
                    "p_inj_mw": _round(b.p_inj_mw, 3),
                    "q_inj_mvar": _round(b.q_inj_mvar, 3),
                }
            )
        for br in r.branches:
            branches_rows.append(
                {
                    "scenario": r.scenario_id,
                    "branch": br.branch_id,
                    "kind": br.kind,
                    "from_bus": br.from_bus,
                    "to_bus": br.to_bus,
                    "p_from_mw": _round(br.p_from_mw, 3),
                    "q_from_mvar": _round(br.q_from_mvar, 3),
                    "p_to_mw": _round(br.p_to_mw, 3),
                    "q_to_mvar": _round(br.q_to_mvar, 3),
                    "i_a": _round(br.i_a, 1),
                    "loss_mw": _round(br.loss_mw, 4),
                    "loading_pct": _round(br.loading_pct, 1),
                }
            )
            for c in br.conductors:
                conductors_rows.append(
                    {
                        "scenario": r.scenario_id,
                        "line": c.line_id,
                        "zone": c.zone_id,
                        "t_c": _round(c.t_c, 2),
                        "ampacity_a": _round(c.ampacity_a, 0),
                        "q_joule_wpm": _round(c.q_joule_wpm, 2),
                        "q_solar_wpm": _round(c.q_solar_wpm, 2),
                        "q_conv_wpm": _round(c.q_conv_wpm, 2),
                        "q_rad_wpm": _round(c.q_rad_wpm, 2),
                        "overload": c.overload,
                    }
                )
        for t in r.transformers:
            transformers_rows.append(
                {
                    "scenario": r.scenario_id,
                    "transformer": t.transformer_id,
                    "s_mva": _round(t.s_mva, 2),
                    "p0_kw": _round(t.p0_kw, 1),
                    "pk_kw": _round(t.pk_kw, 1),
                    "loss_mw": _round(t.loss_mw, 4),
                }
            )

    _write_csv(out / "buses.csv", _FIELDNAMES_BUSES, buses_rows)
    _write_csv(out / "branches.csv", _FIELDNAMES_BRANCHES, branches_rows)
    _write_csv(out / "conductors.csv", _FIELDNAMES_CONDUCTORS, conductors_rows)
    _write_csv(out / "transformers.csv", _FIELDNAMES_TRANSFORMERS, transformers_rows)

    summary = {
        "scenarios": [
            {
                "id": r.scenario_id,
                "converged": r.converged,
                "nr_iterations": r.nr_iterations,
                "coupling_passes": r.coupling_passes,
                "max_mismatch_pu": r.max_mismatch_pu,
                "max_delta_t_k": r.max_delta_t_k,
                "total_loss_mw": r.total_loss_mw,
                "total_loss_fixed_r_mw": r.total_loss_fixed_r_mw,
                "warnings": list(r.warnings),
            }
            for r in results
        ]
    }
    with (out / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=_json_fallback)


def _round(v: float, nd: int) -> float | None:
    """Round a value for display; preserve NaN as ``None`` in CSV output."""
    if v is None:
        return None
    try:
        if math.isnan(v) or math.isinf(v):
            return None
    except TypeError:
        return None
    return round(float(v), nd)


def _json_fallback(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return str(obj)
