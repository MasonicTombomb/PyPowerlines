"""Tests for the YAML study loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from pypowerlines.errors import InputError
from pypowerlines.io import load_study

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "north_wales" / "study.yaml"


def test_example_study_loads() -> None:
    study = load_study(EXAMPLE)
    assert study.id == "NW-REF"
    assert len(study.grid.buses) == 10
    assert len(study.grid.lines) == 8
    assert len(study.grid.transformers) == 2
    assert len(study.scenarios) == 3


def test_example_study_resolves_zones_on_spans() -> None:
    study = load_study(EXAMPLE)
    wylf_pent = next(line for line in study.grid.lines if line.id == "WYLF-PENT")
    assert wylf_pent.spans[0].zone.id == "anglesey"
    assert wylf_pent.spans[0].conductor.name == "ACSR Zebra"


def test_missing_file_raises_input_error(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        load_study(tmp_path / "nope.yaml")


def test_invalid_study_collects_many_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    grid = tmp_path / "grid.yaml"
    grid.write_text(
        """\
schema_version: "1.0"
buses:
  - {id: A, kv: 400, type: slack}
  - {id: B, kv: 400, type: pq}
lines:
  - id: L
    from_bus: A
    to_bus: NOPE
    circuits: 1
    spans:
      - {length_m: -5, tower: NoSuchTower, conductor: NoConductor, zone: NoZone}
"""
    )
    bad.write_text(
        f"""\
schema_version: "1.0"
id: bad
grid: {grid.name}
scenarios:
  - id: s
    name: s
    ambient_c: 10
    wind_ms: 1
"""
    )
    with pytest.raises(InputError) as excinfo:
        load_study(bad)
    # Expect at least the reference resolution error, length error, and
    # island-without-slack (no slack because A has no connections).
    assert len(excinfo.value.errors) >= 2
