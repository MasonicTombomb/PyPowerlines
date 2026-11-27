"""End-to-end CLI test: run the example study and check output files.

Exercises :mod:`pypowerlines.cli`, :mod:`pypowerlines.io.writer` and
:mod:`pypowerlines.report` together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pypowerlines.cli import EXIT_OK, main

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "north_wales" / "study.yaml"


def test_cli_run_writes_results(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "results"
    exit_code = main([
        "run",
        str(EXAMPLE),
        "--out",
        str(out),
        "--scenario",
        "winter_peak",
    ])
    assert exit_code == EXIT_OK
    assert (out / "buses.csv").is_file()
    assert (out / "branches.csv").is_file()
    assert (out / "conductors.csv").is_file()
    assert (out / "transformers.csv").is_file()
    assert (out / "summary.json").is_file()

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert len(summary["scenarios"]) == 1
    assert summary["scenarios"][0]["id"] == "winter_peak"
    assert summary["scenarios"][0]["converged"] is True

    captured = capsys.readouterr()
    assert "PyPowerlines study" in captured.out
    assert "total losses" in captured.out


def test_cli_validate_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["validate", str(EXAMPLE)])
    assert exit_code == EXIT_OK
    captured = capsys.readouterr()
    assert "NW-REF" in captured.out


def test_cli_library_lists_builtin(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["library"])
    assert exit_code == EXIT_OK
    captured = capsys.readouterr()
    assert "ACSR Zebra" in captured.out
    assert "SGT_240MVA_400_132" in captured.out


def test_cli_run_no_coupling_differs_from_coupled(tmp_path: Path) -> None:
    coupled_out = tmp_path / "coupled"
    main(["run", str(EXAMPLE), "--out", str(coupled_out), "--scenario", "heatwave"])
    coupled_summary = json.loads((coupled_out / "summary.json").read_text())

    fixed_out = tmp_path / "fixed"
    main(["run", str(EXAMPLE), "--out", str(fixed_out), "--scenario", "heatwave", "--no-coupling"])
    fixed_summary = json.loads((fixed_out / "summary.json").read_text())

    coupled_loss = coupled_summary["scenarios"][0]["total_loss_mw"]
    fixed_loss = fixed_summary["scenarios"][0]["total_loss_mw"]
    # Heatwave: coupled losses are higher than the fixed-R losses because
    # hot conductors resist more (PPL-REF-001 section 5).
    assert coupled_loss > fixed_loss
