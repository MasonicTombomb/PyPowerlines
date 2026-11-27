"""Admittance matrix, power flow and coupled electro-thermal solvers.

The main entry points are:

* :func:`solve_scenario` -- orchestrates one coupled snapshot.
* :func:`solve_powerflow` -- the inner Newton-Raphson power flow.
* :func:`build_ybus` -- assemble the bus admittance matrix.

Result dataclasses live in :mod:`pypowerlines.model` because they belong
on the information layer rather than the solver layer (PPL-SDS-001
section 5.3).
"""

from .coupled import solve_scenario
from .powerflow import PowerFlowSolution, build_ybus, solve_powerflow

__all__ = [
    "PowerFlowSolution",
    "build_ybus",
    "solve_powerflow",
    "solve_scenario",
]
