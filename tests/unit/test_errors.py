"""Tests for :mod:`pypowerlines.errors`."""

import dataclasses
import pickle

import annunciator
import pytest
from annunciator import CodedError, Severity

from pypowerlines.errors import (
    CouplingNotConverged,
    InputError,
    ModelError,
    NumericalError,
    PowerFlowDivergence,
    Problem,
    PyPowerlinesError,
    ThermalBracketError,
)

ERROR = Problem("V-004", "grid.yaml:buses", "island {B7, B8} has no slack bus", "error")
WARNING = Problem("V-010", "weather.csv:zone_3", "wind 0.2 m/s below 0.5 m/s", "warning")
INFO = Problem("V-006", "grid.yaml:transformers[0]", "kV differs by 8 %", "info")


def _examples() -> list[PyPowerlinesError]:
    """One instance of every concrete exception class."""
    return [
        InputError([ERROR]),
        PowerFlowDivergence(iterations=20, max_mismatch_pu=0.35, bus_ids=["LEGA1"]),
        ThermalBracketError("WYLF-PENT/3", 2150.0, {"t_amb_c": 35.0}),
        CouplingNotConverged(passes=10, max_delta_t_k=1.5),
        ModelError("Y-bus not square"),
    ]


# -- Problem -----------------------------------------------------------------


def test_problem_str_is_one_console_line() -> None:
    assert str(ERROR) == "E V-004 grid.yaml:buses: island {B7, B8} has no slack bus"
    assert str(WARNING).startswith("W V-010 ")
    assert str(INFO).startswith("I V-006 ")


def test_problem_is_error_only_for_error_severity() -> None:
    assert ERROR.is_error
    assert not WARNING.is_error
    assert not INFO.is_error


def test_problem_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        ERROR.rule = "V-999"  # type: ignore[misc]


# -- Hierarchy and exit codes -------------------------------------------------


def test_base_class_is_annunciator_coded_error() -> None:
    assert issubclass(PyPowerlinesError, CodedError)


@pytest.mark.parametrize(
    ("cls", "parent"),
    [
        (InputError, PyPowerlinesError),
        (NumericalError, PyPowerlinesError),
        (PowerFlowDivergence, NumericalError),
        (ThermalBracketError, NumericalError),
        (CouplingNotConverged, NumericalError),
        (ModelError, PyPowerlinesError),
    ],
)
def test_hierarchy_matches_sds_figure_23(
    cls: type[PyPowerlinesError], parent: type[PyPowerlinesError]
) -> None:
    assert issubclass(cls, parent)


@pytest.mark.parametrize(
    ("cls", "exit_code"),
    [
        (PyPowerlinesError, 1),
        (InputError, 2),
        (NumericalError, 3),
        (PowerFlowDivergence, 3),
        (ThermalBracketError, 3),
        (CouplingNotConverged, 3),
        (ModelError, 1),
    ],
)
def test_exit_codes_match_user_guide(cls: type[PyPowerlinesError], exit_code: int) -> None:
    assert cls.exit_code == exit_code


# -- Message codes ------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "code"),
    list(
        zip(
            _examples(),
            ["PPL-E-0100", "PPL-E-0201", "PPL-E-0202", "PPL-E-0203", "PPL-C-0900"],
            strict=True,
        )
    ),
    ids=lambda v: type(v).__name__ if isinstance(v, Exception) else v,
)
def test_each_error_has_its_catalogue_code(error: PyPowerlinesError, code: str) -> None:
    assert error.code == code
    assert str(error).startswith(f"[{code}] ")
    definition = annunciator.lookup(code)
    assert definition is not None
    assert error.cause == definition.cause
    assert error.remedy == definition.remedy


def test_every_error_has_cause_and_remedy() -> None:
    for error in _examples():
        assert error.cause, type(error).__name__
        assert error.remedy, type(error).__name__


def test_model_error_is_critical() -> None:
    assert ModelError().severity is Severity.CRITICAL


def test_model_error_uses_given_message_but_catalogue_help() -> None:
    error = ModelError("Y-bus not square")
    assert error.message == "Y-bus not square"
    assert "bug" in error.cause


def test_model_error_default_message() -> None:
    assert ModelError().message == "Internal error in PyPowerlines."


# -- InputError ----------------------------------------------------------------


def test_input_error_keeps_all_problems_in_order() -> None:
    error = InputError([ERROR, WARNING, INFO])
    assert error.problems == (ERROR, WARNING, INFO)
    assert error.errors == (ERROR,)
    assert error.warnings == (WARNING,)


def test_input_error_message_counts_errors_and_warnings() -> None:
    error = InputError([ERROR, ERROR, WARNING, INFO])
    assert error.fields == {"n_errors": 2, "n_warnings": 1}
    assert "2 error(s) and 1 warning(s)" in error.message


def test_input_error_accepts_any_iterable() -> None:
    assert InputError(p for p in [ERROR]).problems == (ERROR,)


def test_input_error_describe_lists_every_problem() -> None:
    text = InputError([ERROR, WARNING]).describe()
    assert "Cause:" in text
    assert "Remedy:" in text
    assert f"  {ERROR}" in text
    assert f"  {WARNING}" in text


@pytest.mark.parametrize("problems", [[], [WARNING], [WARNING, INFO]])
def test_input_error_without_error_problem_is_a_bug(problems: list[Problem]) -> None:
    with pytest.raises(ModelError, match="without any 'error' problem"):
        InputError(problems)


# -- Numerical errors -----------------------------------------------------------


def test_power_flow_divergence_records_diagnostics() -> None:
    error = PowerFlowDivergence(iterations=20, max_mismatch_pu=0.35, bus_ids=["A", "B"])
    assert (error.iterations, error.max_mismatch_pu, error.bus_ids) == (20, 0.35, ("A", "B"))
    assert error.fields == {"iterations": 20, "max_mismatch_pu": 0.35, "bus_ids": ["A", "B"]}
    assert "after 20 iterations" in error.message
    assert "0.35 pu" in error.message


def test_power_flow_divergence_bus_ids_optional() -> None:
    assert PowerFlowDivergence(iterations=1, max_mismatch_pu=1.0).bus_ids == ()


def test_thermal_bracket_error_positional_signature_from_adr() -> None:
    # PPL-ADR-001 coding standards: raise ThermalBracketError(span_id, i_a, weather)
    error = ThermalBracketError("S1", 1234.56, {"t_amb_c": 35.0})
    assert (error.span_id, error.i_a, error.weather) == ("S1", 1234.56, {"t_amb_c": 35.0})
    assert "'S1'" in error.message
    assert "1234.6 A" in error.message


def test_thermal_bracket_error_copies_weather() -> None:
    weather = {"t_amb_c": 35.0}
    error = ThermalBracketError("S1", 1.0, weather)
    weather["t_amb_c"] = 0.0
    assert error.weather == {"t_amb_c": 35.0}


def test_thermal_bracket_error_weather_optional() -> None:
    assert ThermalBracketError("S1", 1.0).weather == {}


def test_coupling_not_converged_records_diagnostics() -> None:
    error = CouplingNotConverged(passes=10, max_delta_t_k=1.5)
    assert (error.passes, error.max_delta_t_k) == (10, 1.5)
    assert "after 10 passes" in error.message
    assert "1.5 K" in error.message


# -- Behaviour shared by all errors ---------------------------------------------


@pytest.mark.parametrize("error", _examples(), ids=lambda e: type(e).__name__)
def test_errors_survive_pickling(error: PyPowerlinesError) -> None:
    # Needed to pass failures back from worker processes in a parallel series.
    copy = pickle.loads(pickle.dumps(error))
    assert type(copy) is type(error)
    assert str(copy) == str(error)
    assert copy.__dict__ == error.__dict__


@pytest.mark.parametrize("error", _examples(), ids=lambda e: type(e).__name__)
def test_errors_are_catchable_as_base_class(error: PyPowerlinesError) -> None:
    with pytest.raises(PyPowerlinesError):
        raise error


def test_with_context_adds_data() -> None:
    error = CouplingNotConverged(passes=3, max_delta_t_k=2.0).with_context(timestamp="T1")
    assert error.context == {"timestamp": "T1"}
