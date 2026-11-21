"""Tests for :mod:`pypowerlines.constants`."""

import math

import pytest
import scipy.constants as sc

from pypowerlines import constants
from pypowerlines.constants import EPSILON_0, MU_0, STEFAN_BOLTZMAN

SPEED_OF_LIGHT_M_S = 299_792_458.0  # exact by SI definition

# CODATA 2018 vs 2022 and classical vs measured mu_0 differ by < 1e-9
# relative. Anything looser than this would hide a typo in a digit.
CODATA_REL_TOL = 1e-9


def test_constants_are_plain_floats() -> None:
    for name in constants.__all__:
        assert type(getattr(constants, name)) is float, name


def test_all_lists_every_public_constant() -> None:
    public = {name for name in vars(constants) if name.isupper() and not name.startswith("_")}
    assert set(constants.__all__) == public


def test_mu_0_is_classical_value() -> None:
    assert 4e-7 * math.pi == MU_0


@pytest.mark.parametrize(
    ("value", "reference"),
    [
        (EPSILON_0, sc.epsilon_0),
        (MU_0, sc.mu_0),
        (STEFAN_BOLTZMAN, sc.Stefan_Boltzmann),
    ],
    ids=["epsilon_0", "mu_0", "stefan_boltzmann"],
)
def test_constants_agree_with_codata(value: float, reference: float) -> None:
    assert math.isclose(value, reference, rel_tol=CODATA_REL_TOL)


def test_stefan_boltzmann_matches_exact_si_formula() -> None:
    # sigma = 2 pi^5 k^4 / (15 h^3 c^2), all exact since the 2019 SI.
    exact = 2 * math.pi**5 * sc.k**4 / (15 * sc.h**3 * sc.c**2)
    assert math.isclose(STEFAN_BOLTZMAN, exact, rel_tol=1e-10)


def test_epsilon_mu_give_speed_of_light() -> None:
    c = 1.0 / math.sqrt(EPSILON_0 * MU_0)
    assert math.isclose(c, SPEED_OF_LIGHT_M_S, rel_tol=CODATA_REL_TOL)
