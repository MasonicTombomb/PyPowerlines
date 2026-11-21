"""Exception types raised by PyPowerlines.

Every exception the package raises on purpose is a subclass of
:class:`PyPowerlinesError`. The hierarchy follows PPL-SDS-001 section 8
(Table 6 and Figure 23)::

    annunciator.CodedError
    └── PyPowerlinesError          base class of everything below
        ├── InputError             bad input; nothing solved      (exit 2)
        ├── NumericalError         one case failed to solve       (exit 3)
        │   ├── PowerFlowDivergence
        │   ├── ThermalBracketError
        │   └── CouplingNotConverged
        └── ModelError             internal invariant broken: a bug

How each class is handled
-------------------------
.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * - Class
     - Typical causes
     - Handling
   * - :class:`InputError`
     - Missing bus, unknown conductor, negative length, gaps in the
       weather CSV
     - All problems are collected during validation and raised together
       as one exception, before any solving. The CLI exits with code 2.
   * - :class:`NumericalError`
     - Power flow diverges, thermal root not bracketed, coupling not
       converged
     - Stop *that* case, log the diagnostics and mark it failed. A time
       series carries on with the next hour. The CLI exits with code 3
       at the end.
   * - :class:`ModelError`
     - An internal invariant is broken
     - Never caught. Raised immediately with the full traceback, because
       it is a bug in PyPowerlines rather than in the user's data.

Physical limit violations (overloads, voltage out of range, conductor over
its maximum temperature) are **not** exceptions. They are ``PhysicalWarning``
result records that are returned with the results, not raised.

Integration with annunciator
----------------------------
Per PPL-ADR-001 (ADR-006) the exceptions are a PyPowerlines hierarchy, but
they build on :class:`annunciator.CodedError`, so each one carries:

* a **message code** such as ``PPL-E-0201``, defined in the
  :data:`~pypowerlines._log.MESSAGES` catalogue next to its class below;
* a probable **cause** and a **remedy** for the user
  (see :meth:`~annunciator.CodedError.describe`);
* structured **fields** (span id, current, iteration count, ...) that are
  logged as data rather than buried in the message text;
* an :attr:`exit_code` the CLI returns when the error ends the program.

Examples
--------
>>> from pypowerlines.errors import PowerFlowDivergence
>>> err = PowerFlowDivergence(iterations=20, max_mismatch_pu=0.35, bus_ids=["LEGA1"])
>>> str(err)
'[PPL-E-0201] Power flow did not converge after 20 iterations (largest mismatch 0.35 pu).'
>>> err.exit_code
3
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Final, Literal

from annunciator import CodedError, Severity

from ._log import MESSAGES

__all__ = [
    "CouplingNotConverged",
    "InputError",
    "ModelError",
    "NumericalError",
    "PowerFlowDivergence",
    "Problem",
    "ProblemSeverity",
    "PyPowerlinesError",
    "ThermalBracketError",
]


# ---------------------------------------------------------------------------
# Validation findings
# ---------------------------------------------------------------------------

type ProblemSeverity = Literal["error", "warning", "info"]
"""Severity of a validation finding.

``"error"`` findings stop the run. ``"warning"`` and ``"info"`` findings are
reported but do not stop it (PPL-DATA-001, Table 9).
"""

_SEVERITY_LETTER: Final[Mapping[str, str]] = {"error": "E", "warning": "W", "info": "I"}
"""One-letter prefixes used when printing problems, as in the console output."""


@dataclass(frozen=True, slots=True)
class Problem:
    """One finding from input validation.

    Validation does not stop at the first finding. It collects a
    :class:`Problem` for every rule violation, so the user can fix them all
    in one go (PPL-DATA-001 section 8).

    Parameters
    ----------
    rule : str
        Identifier of the validation rule that fired, e.g. ``"V-003"``. See
        the validation rule catalogue in PPL-DATA-001, Table 9.
    path : str
        Location of the offending value: the file name, then a colon, then
        the path inside the file, e.g.
        ``"grid.yaml:lines[3].spans[0].conductor"``.
    message : str
        A human-readable description of the finding, ideally with a
        suggested fix, e.g. ``"'ACSR Zebr' not found (did you mean 'ACSR
        Zebra'?)"``.
    severity : {"error", "warning", "info"}
        How serious the finding is. Only ``"error"`` stops the run.

    Examples
    --------
    >>> p = Problem("V-003", "grid.yaml:lines[3].spans[0].conductor",
    ...             "'ACSR Zebr' not found", "error")
    >>> print(p)
    E V-003 grid.yaml:lines[3].spans[0].conductor: 'ACSR Zebr' not found
    >>> p.is_error
    True
    """

    rule: str
    path: str
    message: str
    severity: ProblemSeverity

    @property
    def is_error(self) -> bool:
        """Whether this finding stops the run (severity ``"error"``)."""
        return self.severity == "error"

    def __str__(self) -> str:
        """Format the finding as one console line: ``<E|W|I> <rule> <path>: <message>``."""
        return f"{_SEVERITY_LETTER[self.severity]} {self.rule} {self.path}: {self.message}"


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class PyPowerlinesError(CodedError):
    """Base class of all exceptions raised by PyPowerlines.

    Catch this to handle any PyPowerlines failure in one place. It is a
    :class:`annunciator.CodedError`, so it accepts the same arguments
    (``message``, ``code``, ``context``, ``cause``, ``remedy`` and
    replacement fields) and has the same attributes.

    Use a specific subclass when raising. This class has no message code of
    its own.

    Attributes
    ----------
    exit_code : int
        Process exit status the CLI uses when this error ends the program.
        ``1`` (generic failure) unless a subclass overrides it.
    """

    exit_code: ClassVar[int] = 1


# ---------------------------------------------------------------------------
# Input errors (0100-0199)
# ---------------------------------------------------------------------------

_INPUT_INVALID: Final[str] = MESSAGES.define(
    100,
    Severity.ERROR,
    "Input validation failed with {n_errors} error(s) and {n_warnings} "
    "warning(s); nothing was solved.",
    cause="One or more input files break a validation rule.",
    remedy="Fix every problem listed below, then run again. Each line gives "
    "the rule, the file and path of the value, and what is wrong.",
    category="input",
    since="0.1.0",
).code


class InputError(PyPowerlinesError):
    """The study inputs are invalid, so nothing was solved.

    Raised once by the loader after **all** validation rules have run,
    carrying every finding at once (errors, and the warnings and info
    findings found alongside them), so the user sees the complete list.

    Code ``PPL-E-0100``. CLI exit code 2.

    Parameters
    ----------
    problems : Iterable[Problem]
        All findings from validation. Must contain at least one finding
        with severity ``"error"``; otherwise the run should not have been
        stopped.

    Attributes
    ----------
    problems : tuple[Problem, ...]
        All findings, in the order they were reported.

    Raises
    ------
    ModelError
        If ``problems`` contains no ``"error"`` finding. Raising an
        :class:`InputError` without one is a bug in the caller.

    Examples
    --------
    >>> err = InputError([
    ...     Problem("V-004", "grid.yaml:buses", "island {B7, B8} has no slack bus", "error"),
    ...     Problem("V-010", "weather.csv:zone_3", "wind 0.2 m/s is below 0.5 m/s", "warning"),
    ... ])
    >>> err.exit_code, len(err.errors), len(err.warnings)
    (2, 1, 1)
    >>> print(err.describe())  # doctest: +NORMALIZE_WHITESPACE
    [PPL-E-0100] Input validation failed with 1 error(s) and 1 warning(s); nothing was solved.
    Cause: One or more input files break a validation rule.
    Remedy: Fix every problem listed below, then run again. Each line gives the rule,
    the file and path of the value, and what is wrong.
      E V-004 grid.yaml:buses: island {B7, B8} has no slack bus
      W V-010 weather.csv:zone_3: wind 0.2 m/s is below 0.5 m/s
    """

    default_code = _INPUT_INVALID
    exit_code: ClassVar[int] = 2

    def __init__(self, problems: Iterable[Problem]) -> None:
        self.problems: tuple[Problem, ...] = tuple(problems)
        n_errors = sum(p.is_error for p in self.problems)
        if n_errors == 0:
            raise ModelError("InputError raised without any 'error' problem.")
        super().__init__(
            n_errors=n_errors,
            n_warnings=sum(p.severity == "warning" for p in self.problems),
        )

    @property
    def errors(self) -> tuple[Problem, ...]:
        """The findings with severity ``"error"``, i.e. the ones that stopped the run."""
        return tuple(p for p in self.problems if p.is_error)

    @property
    def warnings(self) -> tuple[Problem, ...]:
        """The findings with severity ``"warning"``."""
        return tuple(p for p in self.problems if p.severity == "warning")

    def describe(self) -> str:
        """Return the message, cause and remedy, followed by one line per problem.

        Returns
        -------
        str
            Multi-line text suitable for printing to the console.
        """
        lines = [super().describe()]
        lines.extend(f"  {problem}" for problem in self.problems)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Numerical errors (0200-0299)
# ---------------------------------------------------------------------------


class NumericalError(PyPowerlinesError):
    """A solver failed to converge or to find a solution for one case.

    This is a failure of a single case (one snapshot or one hour of a time
    series), not of the whole run: the caller marks that case as failed,
    logs the diagnostics and carries on. The CLI exits with code 3 at the
    end if any case failed. Results for the other cases are still written.

    Abstract grouping class: raise one of its subclasses.
    """

    exit_code: ClassVar[int] = 3


_POWER_FLOW_DIVERGED: Final[str] = MESSAGES.define(
    201,
    Severity.ERROR,
    "Power flow did not converge after {iterations} iterations "
    "(largest mismatch {max_mismatch_pu:.3g} pu).",
    cause="The Newton-Raphson mismatch kept rising or hit the iteration limit, "
    "even after a retry from a flat start.",
    remedy="This usually means an island without a slack bus or a "
    "zero-impedance branch. Check the network around the listed buses.",
    category="numerical",
    since="0.1.0",
).code


class PowerFlowDivergence(NumericalError):  # noqa: N818 - name fixed by PPL-SDS-001 Fig. 23
    """The Newton-Raphson power flow did not converge.

    Raised after the solver has already retried once from a flat start
    (PPL-ALG-001 section 9). Code ``PPL-E-0201``.

    Parameters
    ----------
    iterations : int
        Number of iterations performed before giving up.
    max_mismatch_pu : float
        Largest absolute power mismatch at the last iteration, in per unit.
    bus_ids : Sequence[str], optional
        Buses with the largest mismatch, to point the user at the problem
        area.

    Attributes
    ----------
    iterations : int
    max_mismatch_pu : float
    bus_ids : tuple[str, ...]
        The values passed to the constructor. They are also recorded in
        :attr:`fields`, so they appear as structured data in the log.
    """

    default_code = _POWER_FLOW_DIVERGED

    def __init__(
        self,
        *,
        iterations: int,
        max_mismatch_pu: float,
        bus_ids: Sequence[str] = (),
    ) -> None:
        self.iterations = iterations
        self.max_mismatch_pu = max_mismatch_pu
        self.bus_ids: tuple[str, ...] = tuple(bus_ids)
        super().__init__(
            iterations=iterations,
            max_mismatch_pu=max_mismatch_pu,
            bus_ids=list(self.bus_ids),
        )


_THERMAL_NOT_BRACKETED: Final[str] = MESSAGES.define(
    202,
    Severity.ERROR,
    "No conductor temperature solves the heat balance of span '{span_id}' at {i_a:.1f} A.",
    cause="The heat balance has no sign change between the ambient "
    "temperature and the upper search limit, so the root finder has no "
    "bracket.",
    remedy="Check the current, the conductor data and the weather for this "
    "span. A very high current or extreme weather can push the conductor "
    "temperature above the search limit.",
    category="numerical",
    since="0.1.0",
).code


class ThermalBracketError(NumericalError):
    """The conductor heat-balance root could not be bracketed.

    The steady-state thermal model finds the conductor temperature at
    which heat gain equals heat loss. This error means no root lies between
    the ambient temperature and the upper search limit (PPL-SDS-001,
    physics design rules). Code ``PPL-E-0202``.

    Parameters
    ----------
    span_id : str
        Identifier of the span (or span group) being solved.
    i_a : float
        Conductor current in amperes.
    weather : Mapping[str, float] or None, optional
        The weather values used, e.g. ``{"t_amb_c": 35.0, "wind_ms": 0.2}``.

    Attributes
    ----------
    span_id : str
    i_a : float
    weather : dict[str, float]
        The values passed to the constructor. They are also recorded in
        :attr:`fields`.

    Examples
    --------
    >>> err = ThermalBracketError("WYLF-PENT/3", 2150.0, {"t_amb_c": 35.0})
    >>> err.code, err.span_id
    ('PPL-E-0202', 'WYLF-PENT/3')
    """

    default_code = _THERMAL_NOT_BRACKETED

    def __init__(
        self,
        span_id: str,
        i_a: float,
        weather: Mapping[str, float] | None = None,
    ) -> None:
        self.span_id = span_id
        self.i_a = i_a
        self.weather: dict[str, float] = dict(weather or {})
        super().__init__(span_id=span_id, i_a=i_a, weather=self.weather)


_COUPLING_NOT_CONVERGED: Final[str] = MESSAGES.define(
    203,
    Severity.ERROR,
    "Electro-thermal coupling did not converge after {passes} passes "
    "(largest temperature change {max_delta_t_k:.3g} K).",
    cause="Conductor temperatures kept oscillating between power flow and "
    "thermal passes, even after the relaxation factor was reduced.",
    remedy="Run again with a smaller relaxation factor (--relax), or check "
    "for lines loaded close to their thermal limit.",
    category="numerical",
    since="0.1.0",
).code


class CouplingNotConverged(NumericalError):  # noqa: N818 - name fixed by PPL-SDS-001 Fig. 23
    """The electro-thermal coupling loop did not converge.

    The coupled solve alternates between the power flow (currents from
    resistances) and the thermal model (temperatures, and so resistances,
    from currents). This error means the temperatures did not settle
    (PPL-ALG-001 section 9). Code ``PPL-E-0203``.

    Parameters
    ----------
    passes : int
        Number of coupling passes performed.
    max_delta_t_k : float
        Largest conductor temperature change in the last pass, in kelvin.

    Attributes
    ----------
    passes : int
    max_delta_t_k : float
        The values passed to the constructor. They are also recorded in
        :attr:`fields`.
    """

    default_code = _COUPLING_NOT_CONVERGED

    def __init__(self, *, passes: int, max_delta_t_k: float) -> None:
        self.passes = passes
        self.max_delta_t_k = max_delta_t_k
        super().__init__(passes=passes, max_delta_t_k=max_delta_t_k)


# ---------------------------------------------------------------------------
# Internal errors (0900-0999)
# ---------------------------------------------------------------------------

_INTERNAL: Final[str] = MESSAGES.define(
    900,
    Severity.CRITICAL,
    "Internal error in PyPowerlines.",
    cause="An internal consistency check failed. This is a bug in "
    "PyPowerlines, not a problem with your input data.",
    remedy="Please report it with the full traceback, the log file "
    "(run.log.jsonl) and, if possible, the input files.",
    category="internal",
    since="0.1.0",
).code


class ModelError(PyPowerlinesError):
    """An internal invariant was broken: a bug in PyPowerlines.

    Raise it where something "cannot happen", e.g. a Y-bus that is not
    square, or a result array whose length does not match the number of
    buses. Pass a message that describes the broken invariant::

        raise ModelError(f"Y-bus is {n}x{m}, expected square")

    It is never caught inside PyPowerlines. It propagates with the full
    traceback so the defect can be found (PPL-SDS-001, Table 6). Code
    ``PPL-C-0900``, severity CRITICAL.

    Parameters
    ----------
    message : str, optional
        Description of the broken invariant. Defaults to the catalogue
        text "Internal error in PyPowerlines."
    **kwargs
        Any other :class:`annunciator.CodedError` argument, e.g.
        ``context={"bus_count": n}``.
    """

    default_code = _INTERNAL
    default_severity: ClassVar[Severity] = Severity.CRITICAL
