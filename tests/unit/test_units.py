"""Tests for :mod:`pypowerlines.units`."""

import math
from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pypowerlines import units

type Conversion = Callable[[float], float]

# (forward, inverse, input, expected forward output)
PAIRS: list[tuple[Conversion, Conversion, float, float]] = [
    (units.kv_to_v, units.v_to_kv, 400.0, 400_000.0),
    (units.mm_to_m, units.m_to_mm, 28.0, 0.028),
    (units.ohm_per_km_to_ohm_per_m, units.ohm_per_m_to_ohm_per_km, 250.0, 0.25),
]
PAIR_IDS = ["voltage", "length", "impedance_per_length"]

# Engineering-sized magnitudes. Excludes values near the float limits,
# where scaling by 1e3 would overflow or underflow.
finite_values = st.floats(min_value=-1e12, max_value=1e12, allow_nan=False)


@pytest.mark.parametrize(("forward", "inverse", "value", "expected"), PAIRS, ids=PAIR_IDS)
def test_forward_conversion_known_value(
    forward: Conversion, inverse: Conversion, value: float, expected: float
) -> None:
    assert math.isclose(forward(value), expected, rel_tol=1e-12)


@pytest.mark.parametrize(("forward", "inverse", "value", "expected"), PAIRS, ids=PAIR_IDS)
def test_inverse_conversion_known_value(
    forward: Conversion, inverse: Conversion, value: float, expected: float
) -> None:
    assert math.isclose(inverse(expected), value, rel_tol=1e-12)


@pytest.mark.parametrize(("forward", "inverse"), [p[:2] for p in PAIRS], ids=PAIR_IDS)
@given(value=finite_values)
def test_round_trip_returns_input(forward: Conversion, inverse: Conversion, value: float) -> None:
    assert math.isclose(inverse(forward(value)), value, rel_tol=1e-12, abs_tol=1e-300)


@pytest.mark.parametrize(("forward", "inverse"), [p[:2] for p in PAIRS], ids=PAIR_IDS)
@given(a=finite_values, b=finite_values)
def test_conversions_are_linear(
    forward: Conversion, inverse: Conversion, a: float, b: float
) -> None:
    # Scale-only conversions must satisfy f(a + b) == f(a) + f(b) (no offset).
    assert math.isclose(forward(a + b), forward(a) + forward(b), rel_tol=1e-9, abs_tol=1e-6)


def test_zero_maps_to_zero() -> None:
    for forward, inverse, _, _ in PAIRS:
        assert forward(0.0) == 0.0
        assert inverse(0.0) == 0.0


def test_nan_passes_through_unvalidated() -> None:
    # By design, units does not validate (see module docstring): validation
    # is the job of the input loader.
    assert math.isnan(units.mm_to_m(math.nan))


def test_all_names_exist_and_are_callable() -> None:
    for name in units.__all__:
        assert callable(getattr(units, name)), name
