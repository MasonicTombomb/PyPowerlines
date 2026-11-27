"""Network data model: validated, immutable snapshot of a study.

Every object in this package is a frozen dataclass containing only plain
values and references to other model objects. After :class:`Study` is built
by :mod:`pypowerlines.io`, no module may mutate it: results are produced as
separate objects keyed by the same ids (PPL-SDS-001 section 5.4).

Unit convention (PPL-SDS-001 section 1.3): values that cross a module
boundary are stored in SI. The only exceptions are temperature (``°C`` at
interfaces and ``K`` inside radiative calculations) and voltages which are
kept in volts here but reported in kilovolts.
"""

from __future__ import annotations

from .components import (
    Bus,
    BusType,
    ConductorType,
    Generator,
    Grid,
    Line,
    Load,
    Span,
    TowerType,
    Transformer,
    TransformerType,
    WeatherZone,
)
from .results import (
    BranchResult,
    BusResult,
    ConductorResult,
    SnapshotResult,
    TransformerResult,
)
from .scenario import Scenario, SolverOptions, Study
from .weather import WeatherState

__all__ = [
    "BranchResult",
    "Bus",
    "BusResult",
    "BusType",
    "ConductorResult",
    "ConductorType",
    "Generator",
    "Grid",
    "Line",
    "Load",
    "Scenario",
    "SnapshotResult",
    "SolverOptions",
    "Span",
    "Study",
    "TowerType",
    "Transformer",
    "TransformerResult",
    "TransformerType",
    "WeatherState",
    "WeatherZone",
]
