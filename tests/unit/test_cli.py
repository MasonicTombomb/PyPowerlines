"""Tests for :mod:`pypowerlines.cli`."""

import argparse

import annunciator
import pytest
from annunciator.testing import EventCapture

import pypowerlines
from pypowerlines import cli
from pypowerlines.cli import EXIT_INTERRUPTED, EXIT_OK, build_parser, main
from pypowerlines.errors import (
    CouplingNotConverged,
    InputError,
    ModelError,
    PowerFlowDivergence,
    Problem,
    ThermalBracketError,
)


def _raise_from_dispatch(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    """Make the CLI's command dispatch raise ``exc``.

    Exercises the CLI's error handling without needing real commands.
    """

    def fake_dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
        raise exc

    monkeypatch.setattr(cli, "_dispatch", fake_dispatch)


# -- Basics ----------------------------------------------------------------------


def test_version_is_set() -> None:
    assert pypowerlines.__version__


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert pypowerlines.__version__ in capsys.readouterr().out


def test_no_arguments_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_OK
    assert "usage: pypowerlines" in capsys.readouterr().out


# -- Verbosity ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "level"),
    [
        ([], "INFO"),
        (["-v"], "DEBUG"),
        (["--verbose"], "DEBUG"),
        (["-q"], "WARNING"),
        (["--quiet"], "WARNING"),
    ],
)
def test_verbosity_flags_set_log_level(argv: list[str], level: str) -> None:
    assert build_parser().parse_args(argv).log_level == level


def test_verbose_and_quiet_are_mutually_exclusive(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["-v", "-q"])
    assert exc.value.code == 2
    assert "not allowed with" in capsys.readouterr().err


def test_verbose_shows_debug_events(annunciator_events: EventCapture) -> None:
    main(["-v"])
    annunciator_events.assert_logged(severity="DEBUG", text="PyPowerlines started")


def test_default_level_hides_debug_events(annunciator_events: EventCapture) -> None:
    main([])
    annunciator_events.assert_not_logged(severity="DEBUG", logger="pypowerlines.cli")


# -- Logging lifecycle ----------------------------------------------------------------


def test_logging_shut_down_after_success() -> None:
    main([])
    assert not annunciator.is_configured()


def test_logging_shut_down_after_reraise(monkeypatch: pytest.MonkeyPatch) -> None:
    _raise_from_dispatch(monkeypatch, ModelError("boom"))
    with pytest.raises(ModelError):
        main([])
    assert not annunciator.is_configured()


def test_help_and_version_do_not_configure_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "configure_logging", calls.append)
    with pytest.raises(SystemExit):
        main(["--help"])
    assert calls == []


# -- Exception to exit-code mapping ----------------------------------------------------


def test_input_error_exits_2_and_logs_every_problem(
    monkeypatch: pytest.MonkeyPatch, annunciator_events: EventCapture
) -> None:
    problems = [
        Problem("V-004", "grid.yaml:buses", "no slack", "error"),
        Problem("V-010", "weather.csv:z3", "wind low", "warning"),
    ]
    _raise_from_dispatch(monkeypatch, InputError(problems))

    assert main([]) == 2
    annunciator_events.assert_logged(severity="ERROR", rule="V-004", path="grid.yaml:buses")
    annunciator_events.assert_logged(severity="WARNING", rule="V-010")
    annunciator_events.assert_logged("PPL-E-0100", count=1)


@pytest.mark.parametrize(
    "error",
    [
        PowerFlowDivergence(iterations=20, max_mismatch_pu=0.3),
        ThermalBracketError("S1", 2000.0),
        CouplingNotConverged(passes=10, max_delta_t_k=1.0),
    ],
    ids=lambda e: type(e).__name__,
)
def test_numerical_error_exits_3_and_logs_code(
    monkeypatch: pytest.MonkeyPatch,
    annunciator_events: EventCapture,
    error: PowerFlowDivergence | ThermalBracketError | CouplingNotConverged,
) -> None:
    _raise_from_dispatch(monkeypatch, error)

    assert main([]) == 3
    event = annunciator_events.assert_logged(error.code, severity="ERROR")
    assert event.fields == error.fields


def test_keyboard_interrupt_exits_130(
    monkeypatch: pytest.MonkeyPatch, annunciator_events: EventCapture
) -> None:
    _raise_from_dispatch(monkeypatch, KeyboardInterrupt())

    assert main([]) == EXIT_INTERRUPTED == 130
    annunciator_events.assert_logged(severity="WARNING", text="Interrupted")


def test_model_error_is_logged_with_traceback_and_reraised(
    monkeypatch: pytest.MonkeyPatch, annunciator_events: EventCapture
) -> None:
    _raise_from_dispatch(monkeypatch, ModelError("Y-bus not square"))

    with pytest.raises(ModelError, match="Y-bus not square"):
        main([])
    event = annunciator_events.assert_logged("PPL-C-0900")
    assert event.exception is not None


def test_unexpected_exception_is_logged_and_reraised(
    monkeypatch: pytest.MonkeyPatch, annunciator_events: EventCapture
) -> None:
    _raise_from_dispatch(monkeypatch, KeyError("oops"))

    with pytest.raises(KeyError):
        main([])
    event = annunciator_events.assert_logged(severity="ERROR", text="Unexpected internal error")
    assert event.exception is not None
