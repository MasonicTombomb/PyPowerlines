"""Result summaries for the console and the run log.

:mod:`pypowerlines.io.writer` owns the CSV / JSON files. This module adds
a compact human-readable summary that the CLI prints for each scenario
(PPL-UG-001 section 5 "Example session"), and a line of structured log
data per run.
"""

from __future__ import annotations

from collections.abc import Sequence
from io import StringIO
from typing import Final

from pypowerlines._log import get_logger
from pypowerlines.model import SnapshotResult, Study

__all__ = ["format_summary", "log_summary"]

_log = get_logger(__name__)


_LINE: Final[str] = "-" * 60


def format_summary(study: Study, results: Sequence[SnapshotResult]) -> str:
    """Return the per-scenario summary block as a single string.

    Parameters
    ----------
    study : Study
    results : Sequence[SnapshotResult]

    Returns
    -------
    str
        Multi-line summary suitable for printing to the console.
    """
    buf = StringIO()
    print(f"PyPowerlines study {study.id!r}", file=buf)
    print(
        f"  {len(study.grid.buses)} buses, {len(study.grid.lines)} lines, "
        f"{len(study.grid.transformers)} transformers",
        file=buf,
    )
    for r in results:
        print(_LINE, file=buf)
        scn = _find_scenario_name(study, r.scenario_id)
        print(f"Scenario {r.scenario_id} ({scn})", file=buf)
        print(
            f"  power flow  iter {r.nr_iterations}  mismatch {r.max_mismatch_pu:.2e} pu",
            file=buf,
        )
        print(
            f"  coupling    pass {r.coupling_passes}  max dT {r.max_delta_t_k:.3g} K",
            file=buf,
        )
        print(f"  total losses  {r.total_loss_mw:.2f} MW", file=buf)
        if r.total_loss_fixed_r_mw == r.total_loss_fixed_r_mw:  # not NaN
            delta_pct = (
                (r.total_loss_mw - r.total_loss_fixed_r_mw)
                / r.total_loss_fixed_r_mw
                * 100.0
                if r.total_loss_fixed_r_mw > 0
                else 0.0
            )
            print(
                f"  R at 20 °C    {r.total_loss_fixed_r_mw:.2f} MW"
                f"  ({delta_pct:+.1f} %)",
                file=buf,
            )

        hottest = _hottest_line(r)
        if hottest is not None:
            line_id, zone_id, t_c, loading_pct = hottest
            print(
                f"  hottest line  {line_id} ({zone_id}) {t_c:.1f} °C"
                f"  ({loading_pct:.0f}% of rating)",
                file=buf,
            )
        lowest_bus = min(r.buses, key=lambda b: b.v_pu, default=None)
        if lowest_bus is not None:
            print(
                f"  lowest V      {lowest_bus.bus_id} {lowest_bus.v_pu:.3f} pu",
                file=buf,
            )
        overloads = [c for b in r.branches for c in b.conductors if c.overload]
        print(f"  overloads     {len(overloads)}", file=buf)
        if r.warnings:
            print(f"  warnings      {len(r.warnings)}", file=buf)
            for w in r.warnings[:5]:
                print(f"    - {w}", file=buf)
    return buf.getvalue()


def log_summary(study: Study, results: Sequence[SnapshotResult]) -> None:
    """Emit one structured log event per scenario with the totals."""
    for r in results:
        _log.info(
            "Scenario solved.",
            study_id=study.id,
            scenario_id=r.scenario_id,
            converged=r.converged,
            nr_iterations=r.nr_iterations,
            coupling_passes=r.coupling_passes,
            total_loss_mw=r.total_loss_mw,
            total_loss_fixed_r_mw=r.total_loss_fixed_r_mw,
            warnings=len(r.warnings),
        )


def _find_scenario_name(study: Study, scenario_id: str) -> str:
    for s in study.scenarios:
        if s.id == scenario_id:
            return s.name
    return scenario_id


def _hottest_line(result: SnapshotResult) -> tuple[str, str, float, float] | None:
    best: tuple[str, str, float, float] | None = None
    for br in result.branches:
        if br.kind != "line":
            continue
        for c in br.conductors:
            if best is None or c.t_c > best[2]:
                best = (br.branch_id, c.zone_id, c.t_c, br.loading_pct)
    return best
