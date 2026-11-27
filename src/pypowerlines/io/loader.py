"""Load and validate a study from YAML files.

The loader is the one place in PyPowerlines that touches the filesystem
for input and parses YAML (PPL-SDS-001 section 5.3 dependency rules).
It produces a fully-populated :class:`~pypowerlines.model.Study`;
callers downstream never see raw strings.

Validation philosophy
---------------------
Every problem is collected as a :class:`~pypowerlines.errors.Problem`
before stopping the run, so the user sees the full list in one pass
(PPL-DATA-001 section 8). The loader stops numerical work early by
raising :class:`~pypowerlines.errors.InputError` if any ``"error"``
findings were collected.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

import yaml

from pypowerlines.errors import InputError, Problem
from pypowerlines.library import Library, builtin_library
from pypowerlines.model import (
    Bus,
    ConductorType,
    Generator,
    Grid,
    Line,
    Load,
    Scenario,
    SolverOptions,
    Span,
    Study,
    TowerType,
    Transformer,
    TransformerType,
    WeatherZone,
)

__all__ = ["load_study"]


# ---------------------------------------------------------------------------
# Validation thresholds
# ---------------------------------------------------------------------------

_KV_EQUALITY_TOL: Final[float] = 1e-6
"""Tolerance for comparing nominal line-end voltages (V-005)."""

_KV_MISMATCH_FRACTION: Final[float] = 0.1
"""Maximum fractional kV mismatch between a transformer type and its bus (V-006)."""

_MIN_RELIABLE_WIND_MS: Final[float] = 0.5
"""Winds below this are flagged by V-010 as rating-uncertain (PPL-CH-001 CS-14)."""


# ---------------------------------------------------------------------------
# Small typed helpers
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a plain dict.

    Parameters
    ----------
    path : pathlib.Path

    Returns
    -------
    dict[str, Any]

    Raises
    ------
    InputError
        If the file is missing or not a mapping.
    """
    if not path.is_file():
        raise InputError([Problem("V-001", str(path), "file not found", "error")])
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        msg = f"top level must be a mapping, got {type(data).__name__}"
        raise InputError([Problem("V-001", str(path), msg, "error")])
    return data


class _Collector:
    """Accumulates problems during validation.

    Keeps the loader code close to how the data document reads, with one
    ``collector.error(...)`` line per rule.
    """

    def __init__(self) -> None:
        self.problems: list[Problem] = []

    def error(self, rule: str, path: str, message: str) -> None:
        self.problems.append(Problem(rule, path, message, "error"))

    def warning(self, rule: str, path: str, message: str) -> None:
        self.problems.append(Problem(rule, path, message, "warning"))

    def info(self, rule: str, path: str, message: str) -> None:
        self.problems.append(Problem(rule, path, message, "info"))

    def has_errors(self) -> bool:
        return any(p.is_error for p in self.problems)


# ---------------------------------------------------------------------------
# Library loading
# ---------------------------------------------------------------------------


def _load_library(extra_paths: Iterable[Path], collector: _Collector) -> Library:
    """Return the built-in library overlaid with any user YAML files.

    Parameters
    ----------
    extra_paths : Iterable[pathlib.Path]
        Paths to user library YAML files. Each must be a mapping with
        optional keys ``conductors``, ``towers``, ``transformers``.
    collector : _Collector
    """
    lib = builtin_library()
    for p in extra_paths:
        data = _read_yaml(p)
        conductors = {
            c["name"]: _make_conductor(c, f"{p}:conductors", collector)
            for c in data.get("conductors", []) or []
        }
        towers = {
            t["name"]: _make_tower(t, f"{p}:towers", collector)
            for t in data.get("towers", []) or []
        }
        transformers = {
            t["name"]: _make_transformer_type(t, f"{p}:transformers", collector)
            for t in data.get("transformers", []) or []
        }
        lib = lib.merged_with(
            Library(conductors=conductors, towers=towers, transformers=transformers)
        )
    return lib


def _make_conductor(d: Mapping[str, Any], path: str, collector: _Collector) -> ConductorType:
    name = d.get("name", "<unnamed>")
    try:
        return ConductorType(
            name=str(name),
            diameter_m=float(d["diameter_mm"]) * 1e-3,
            r20_ohm_per_m=float(d["r20_ohm_per_km"]) * 1e-3,
            alpha_per_k=float(d.get("alpha_per_k", 0.00403)),
            sub_conductors=int(d.get("sub_conductors", 1)),
            bundle_spacing_m=float(d.get("bundle_spacing_m", 0.0)),
            absorptivity=float(d.get("absorptivity", 0.8)),
            emissivity=float(d.get("emissivity", 0.7)),
            t_max_c=float(d.get("t_max_c", 75.0)),
            mass_kg_per_m=float(d.get("mass_kg_per_m", 0.0)),
            uts_kn=float(d.get("uts_kn", 0.0)),
        )
    except (KeyError, TypeError, ValueError) as err:
        collector.error("V-001", f"{path}:{name}", f"invalid conductor: {err}")
        return ConductorType(name=str(name), diameter_m=0.028, r20_ohm_per_m=1e-4)


def _make_tower(d: Mapping[str, Any], path: str, collector: _Collector) -> TowerType:
    name = d.get("name", "<unnamed>")
    try:
        phases = tuple((float(x), float(y)) for x, y in d["phases_m"])
        earth = tuple((float(x), float(y)) for x, y in d.get("earth_wires_m", []) or [])
        return TowerType(name=str(name), phases_m=phases, earth_wires_m=earth)
    except (KeyError, TypeError, ValueError) as err:
        collector.error("V-001", f"{path}:{name}", f"invalid tower: {err}")
        return TowerType(name=str(name), phases_m=((0.0, 0.0),) * 3)


def _make_transformer_type(
    d: Mapping[str, Any], path: str, collector: _Collector
) -> TransformerType:
    name = d.get("name", "<unnamed>")
    try:
        return TransformerType(
            name=str(name),
            rating_mva=float(d["rating_mva"]),
            hv_kv=float(d["hv_kv"]),
            lv_kv=float(d["lv_kv"]),
            z_pct=float(d["z_pct"]),
            x_over_r=float(d.get("x_over_r", 40.0)),
            p0_kw=float(d.get("p0_kw", 0.0)),
            pk_kw=float(d.get("pk_kw", 0.0)),
            tap_step_pct=float(d.get("tap_step_pct", 1.25)),
            tap_min=int(d.get("tap_min", -10)),
            tap_max=int(d.get("tap_max", 10)),
        )
    except (KeyError, TypeError, ValueError) as err:
        collector.error("V-001", f"{path}:{name}", f"invalid transformer type: {err}")
        return TransformerType(name=str(name), rating_mva=1.0, hv_kv=1.0, lv_kv=1.0, z_pct=1.0)


# ---------------------------------------------------------------------------
# Grid loading
# ---------------------------------------------------------------------------


def _make_bus(d: Mapping[str, Any], path: str, collector: _Collector) -> Bus:
    bus_id = str(d.get("id", "<unnamed>"))
    type_str = str(d.get("type", "pq")).lower()
    if type_str not in ("slack", "pv", "pq"):
        collector.error("V-001", f"{path}:{bus_id}.type", f"unknown bus type {type_str!r}")
        type_str = "pq"
    try:
        kv = float(d["kv"])
    except KeyError, TypeError, ValueError:
        collector.error("V-007", f"{path}:{bus_id}.kv", "missing or non-numeric kv")
        kv = 1.0
    if kv <= 0:
        collector.error("V-007", f"{path}:{bus_id}.kv", f"kv must be positive, got {kv}")

    return Bus(
        id=bus_id,
        name=str(d.get("name", bus_id)),
        kv=kv,
        type=type_str,  # type: ignore[arg-type]
        v_set_pu=float(d.get("v_set_pu", 1.0)),
        lat=_opt_float(d.get("lat")),
        lon=_opt_float(d.get("lon")),
    )


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except TypeError, ValueError:
        return None


def _make_zone(d: Mapping[str, Any], path: str, collector: _Collector) -> WeatherZone:
    zone_id = str(d.get("id", "<unnamed>"))
    try:
        lat = float(d["latitude"])
    except KeyError, TypeError, ValueError:
        collector.error("V-001", f"{path}:{zone_id}.latitude", "missing or non-numeric latitude")
        lat = 0.0
    return WeatherZone(
        id=zone_id,
        name=str(d.get("name", zone_id)),
        latitude_deg=lat,
        elevation_m=float(d.get("elevation_m", 0.0)),
        temperature_offset_k=float(d.get("temperature_offset_k", 0.0)),
        wind_multiplier=float(d.get("wind_multiplier", 1.0)),
    )


def _make_line(  # noqa: PLR0913, PLR0917 -- one validator per entity field
    d: Mapping[str, Any],
    path: str,
    buses: dict[str, Bus],
    zones: dict[str, WeatherZone],
    library: Library,
    collector: _Collector,
) -> Line | None:
    line_id = str(d.get("id", "<unnamed>"))
    try:
        from_bus = buses[d["from_bus"]]
        to_bus = buses[d["to_bus"]]
    except KeyError as err:
        collector.error("V-003", f"{path}:{line_id}", f"bus reference not found: {err}")
        return None
    if abs(from_bus.kv - to_bus.kv) > _KV_EQUALITY_TOL:
        collector.error(
            "V-005",
            f"{path}:{line_id}",
            f"line ends at different kV: {from_bus.id} ({from_bus.kv}) "
            f"vs {to_bus.id} ({to_bus.kv})",
        )
    circuits = int(d.get("circuits", 1))
    spans_data = d.get("spans", []) or []
    spans: list[Span] = []
    for i, s in enumerate(spans_data):
        count = int(s.get("count", 1))
        for _ in range(count):
            try:
                tower = library.get_tower(s["tower"])
                conductor = library.get_conductor(s["conductor"])
                zone = zones[s["zone"]]
            except KeyError as err:
                collector.error(
                    "V-003", f"{path}:{line_id}.spans[{i}]", f"unresolved reference: {err}"
                )
                continue
            length_m = float(s["length_m"])
            if length_m <= 0:
                collector.error(
                    "V-007", f"{path}:{line_id}.spans[{i}].length_m", "must be positive"
                )
            spans.append(
                Span(
                    length_m=length_m,
                    tower=tower,
                    conductor=conductor,
                    zone=zone,
                    elevation_m=_opt_float(s.get("elevation_m")),
                    azimuth_deg=_opt_float(s.get("azimuth_deg")),
                )
            )
    if not spans:
        collector.error("V-001", f"{path}:{line_id}", "line has no spans")
        return None
    return Line(id=line_id, from_bus=from_bus, to_bus=to_bus, circuits=circuits, spans=tuple(spans))


def _make_transformer(
    d: Mapping[str, Any],
    path: str,
    buses: dict[str, Bus],
    library: Library,
    collector: _Collector,
) -> Transformer | None:
    tid = str(d.get("id", "<unnamed>"))
    try:
        hv_bus = buses[d["hv_bus"]]
        lv_bus = buses[d["lv_bus"]]
        type_obj = library.get_transformer(d["type"])
    except KeyError as err:
        collector.error("V-003", f"{path}:{tid}", f"unresolved reference: {err}")
        return None
    if abs(hv_bus.kv - type_obj.hv_kv) / type_obj.hv_kv > _KV_MISMATCH_FRACTION:
        collector.error(
            "V-006",
            f"{path}:{tid}",
            f"HV bus {hv_bus.kv} kV mismatches type {type_obj.hv_kv} kV by >10%",
        )
    if abs(lv_bus.kv - type_obj.lv_kv) / type_obj.lv_kv > _KV_MISMATCH_FRACTION:
        collector.error(
            "V-006",
            f"{path}:{tid}",
            f"LV bus {lv_bus.kv} kV mismatches type {type_obj.lv_kv} kV by >10%",
        )
    return Transformer(
        id=tid,
        hv_bus=hv_bus,
        lv_bus=lv_bus,
        type=type_obj,
        count=int(d.get("count", 1)),
        tap_pos=int(d.get("tap_pos", 0)),
    )


def _make_load(
    d: Mapping[str, Any], path: str, buses: dict[str, Bus], collector: _Collector
) -> Load | None:
    lid = str(d.get("id", "<unnamed>"))
    try:
        bus = buses[d["bus"]]
    except KeyError:
        collector.error("V-003", f"{path}:{lid}.bus", f"bus {d.get('bus')!r} not found")
        return None
    return Load(id=lid, bus=bus, p_mw=float(d.get("p_mw", 0.0)), q_mvar=float(d.get("q_mvar", 0.0)))


def _make_generator(
    d: Mapping[str, Any], path: str, buses: dict[str, Bus], collector: _Collector
) -> Generator | None:
    gid = str(d.get("id", "<unnamed>"))
    try:
        bus = buses[d["bus"]]
    except KeyError:
        collector.error("V-003", f"{path}:{gid}.bus", f"bus {d.get('bus')!r} not found")
        return None
    return Generator(
        id=gid,
        bus=bus,
        p_mw=float(d.get("p_mw", 0.0)),
        v_set_pu=float(d.get("v_set_pu", bus.v_set_pu)),
        q_min_mvar=float(d.get("q_min_mvar", float("-inf"))),
        q_max_mvar=float(d.get("q_max_mvar", float("inf"))),
    )


def _load_grid(path: Path, library: Library, collector: _Collector) -> Grid:
    data = _read_yaml(path)
    # Zones first (lines reference them).
    zones = {
        z.id: z
        for z in (_make_zone(z, f"{path}:zones", collector) for z in data.get("zones", []) or [])
    }
    buses = {
        b.id: b
        for b in (_make_bus(b, f"{path}:buses", collector) for b in data.get("buses", []) or [])
    }
    _check_ids_unique(data.get("buses") or [], "id", "V-002", f"{path}:buses", collector)
    _check_ids_unique(data.get("zones") or [], "id", "V-002", f"{path}:zones", collector)

    lines_raw = data.get("lines", []) or []
    lines: list[Line] = []
    for d in lines_raw:
        line = _make_line(d, f"{path}:lines", buses, zones, library, collector)
        if line is not None:
            lines.append(line)

    transformers: list[Transformer] = []
    for d in data.get("transformers", []) or []:
        tx = _make_transformer(d, f"{path}:transformers", buses, library, collector)
        if tx is not None:
            transformers.append(tx)

    loads: list[Load] = []
    for d in data.get("loads", []) or []:
        ld = _make_load(d, f"{path}:loads", buses, collector)
        if ld is not None:
            loads.append(ld)

    generators: list[Generator] = []
    for d in data.get("generators", []) or []:
        g = _make_generator(d, f"{path}:generators", buses, collector)
        if g is not None:
            generators.append(g)

    grid = Grid(
        buses=tuple(buses.values()),
        lines=tuple(lines),
        transformers=tuple(transformers),
        loads=tuple(loads),
        generators=tuple(generators),
        zones=tuple(zones.values()),
    )
    _check_grid_topology(grid, collector)
    return grid


def _check_ids_unique(
    items: list[dict[str, object]], key: str, rule: str, path: str, collector: _Collector
) -> None:
    seen: set[str] = set()
    for i, d in enumerate(items):
        v = str(d.get(key, ""))
        if v in seen:
            collector.error(rule, f"{path}[{i}].{key}", f"duplicate {key}={v!r}")
        seen.add(v)


def _check_grid_topology(grid: Grid, collector: _Collector) -> None:
    """Walk the grid to check island/slack rules and isolated buses."""
    adj: dict[str, set[str]] = {b.id: set() for b in grid.buses}
    for line in grid.lines:
        adj[line.from_bus.id].add(line.to_bus.id)
        adj[line.to_bus.id].add(line.from_bus.id)
    for tx in grid.transformers:
        adj[tx.hv_bus.id].add(tx.lv_bus.id)
        adj[tx.lv_bus.id].add(tx.hv_bus.id)

    seen: set[str] = set()
    islands: list[set[str]] = []
    for b in grid.buses:
        if b.id in seen:
            continue
        stack = [b.id]
        island: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in island:
                continue
            island.add(cur)
            stack.extend(adj[cur])
        seen.update(island)
        islands.append(island)

    slack_ids = {b.id for b in grid.buses if b.type == "slack"}
    for island in islands:
        slacks = island & slack_ids
        if len(slacks) == 0:
            collector.error(
                "V-004",
                "grid:islands",
                f"island with buses {sorted(island)} has no slack bus",
            )
        elif len(slacks) > 1:
            collector.error(
                "V-004",
                "grid:islands",
                f"island {sorted(island)} has multiple slack buses {sorted(slacks)}",
            )

    for b in grid.buses:
        if not adj[b.id]:
            collector.error("V-012", f"grid:buses:{b.id}", "bus has no connections")


# ---------------------------------------------------------------------------
# Scenario and solver options
# ---------------------------------------------------------------------------


def _make_scenario(d: Mapping[str, Any], path: str, collector: _Collector) -> Scenario:
    sid = str(d.get("id", "<unnamed>"))
    try:
        ambient = float(d["ambient_c"])
        wind = float(d["wind_ms"])
    except (KeyError, TypeError, ValueError) as err:
        collector.error("V-001", f"{path}:{sid}", f"missing/invalid ambient_c or wind_ms: {err}")
        ambient = 20.0
        wind = 1.0
    if wind < _MIN_RELIABLE_WIND_MS:
        collector.warning(
            "V-010",
            f"{path}:{sid}.wind_ms",
            f"wind {wind} m/s is below 0.5 m/s (rating uncertainty)",
        )

    return Scenario(
        id=sid,
        name=str(d.get("name", sid)),
        ambient_c=ambient,
        wind_ms=wind,
        irradiance_wm2=float(d.get("irradiance_wm2", 0.0)),
        wind_angle_deg=float(d.get("wind_angle_deg", 90.0)),
        rain_mmh=float(d.get("rain_mmh", 0.0)),
        gen_p_mw={str(k): float(v) for k, v in (d.get("generation", {}) or {}).items()},
        load_p_mw={str(k): float(v) for k, v in (d.get("load_p_mw", {}) or {}).items()},
        load_q_mvar={str(k): float(v) for k, v in (d.get("load_q_mvar", {}) or {}).items()},
    )


def _make_options(d: Mapping[str, Any]) -> SolverOptions:
    return SolverOptions(
        pf_tolerance_pu=float(d.get("pf_tolerance_pu", 1e-8)),
        pf_max_iter=int(d.get("pf_max_iter", 30)),
        coupling=bool(d.get("coupling", True)),
        thermal_tolerance_k=float(d.get("thermal_tolerance_k", 0.1)),
        thermal_max_iter=int(d.get("thermal_max_iter", 20)),
        relaxation=float(d.get("relaxation", 1.0)),
        thermal_model=str(d.get("thermal_model", "ieee738_2012")),
        t_start_c=float(d.get("t_start_c", 20.0)),
        t_max_c=_opt_float(d.get("t_max_c")),
    )


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------


def load_study(study_path: str | Path) -> Study:
    """Load and validate a study from a YAML file.

    Parameters
    ----------
    study_path : str or pathlib.Path
        Path to ``study.yaml``. All other file paths (``grid``,
        ``library[]``) are resolved relative to its directory.

    Returns
    -------
    Study
        Fully-validated, immutable study ready to be solved.

    Raises
    ------
    InputError
        With every finding collected during validation.
    """
    path = Path(study_path)
    collector = _Collector()
    data = _read_yaml(path)
    root = path.parent

    # Library (built-in + user overrides)
    extra_lib_paths = [root / p for p in (data.get("library", []) or [])]
    library = _load_library(extra_lib_paths, collector)

    # Grid
    grid_path = root / data.get("grid", "grid.yaml")
    grid = _load_grid(grid_path, library, collector)

    # Scenarios
    scenarios_data = data.get("scenarios", []) or []
    if not scenarios_data:
        collector.error("V-001", f"{path}:scenarios", "at least one scenario is required")
    scenarios = tuple(_make_scenario(s, f"{path}:scenarios", collector) for s in scenarios_data)

    options = _make_options(data.get("options", {}) or {})

    if collector.has_errors():
        raise InputError(collector.problems)

    return Study(
        id=str(data.get("id", path.stem)),
        name=str(data.get("name", data.get("id", path.stem))),
        frequency_hz=float(data.get("frequency_hz", 50.0)),
        base_mva=float(data.get("base_mva", 100.0)),
        grid=grid,
        scenarios=scenarios,
        options=options,
    )
