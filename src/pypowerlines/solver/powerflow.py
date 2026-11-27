"""Y-bus assembly and Newton-Raphson AC power flow.

Follows PPL-ALG-001 sections 2-3 closely:

* :func:`build_ybus` assembles a dense complex Y-bus from the branch list.
* :func:`solve_powerflow` runs polar Newton-Raphson until the maximum
  power mismatch drops below ``pf_tolerance_pu`` or the iteration limit
  is reached.

The network is small (≤ a few hundred buses in v1, PPL-SDS-001 QR-02), so
a dense NumPy formulation is used. PPL-ALG-001 section 7 notes that
sparse matrices only become necessary beyond ~200 buses; the code here
is organised so the dense call can be swapped for a sparse variant later
without changing the interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from pypowerlines._log import get_logger
from pypowerlines.errors import PowerFlowDivergence
from pypowerlines.model import BusType, Study

from .network import Branch

__all__ = [
    "PowerFlowSolution",
    "build_ybus",
    "solve_powerflow",
]

_log = get_logger(__name__)


_MAX_RETRIES_FROM_FLAT: Final[int] = 1
"""Number of times to retry NR from a flat start after a divergence."""


# ---------------------------------------------------------------------------
# Y-bus
# ---------------------------------------------------------------------------


def build_ybus(n_bus: int, branches: list[Branch]) -> np.ndarray:
    r"""Assemble the complex bus admittance matrix.

    Follows PPL-ALG-001 Figure 2. For each branch with series admittance
    :math:`y`, shunt-half :math:`y_{sh}/2` and tap :math:`t` on the HV
    (from) side:

    * ``Y[f,f] += (y + y_sh/2) / t**2``
    * ``Y[t,t] += y + y_sh/2``
    * ``Y[f,t] -= y / t`` and ``Y[t,f] -= y / t``.

    For a line :math:`t = 1`, which simplifies to the familiar form.

    Parameters
    ----------
    n_bus : int
        Number of buses (rows/cols).
    branches : list[Branch]

    Returns
    -------
    numpy.ndarray
        Complex ``(n_bus, n_bus)`` Y-bus in per unit.
    """
    y = np.zeros((n_bus, n_bus), dtype=complex)
    for br in branches:
        f, t = br.from_idx, br.to_idx
        ys = br.y_series_pu
        yh = br.y_shunt_half_pu
        tap = br.tap
        y[f, f] += (ys + yh) / (tap * tap)
        y[t, t] += ys + yh
        y[f, t] -= ys / tap
        y[t, f] -= ys / tap
    return y


# ---------------------------------------------------------------------------
# Power flow data
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PowerFlowSolution:
    """Converged state of the AC power flow.

    Parameters
    ----------
    v_mag : numpy.ndarray
        Voltage magnitudes per unit, shape ``(n_bus,)``.
    v_ang : numpy.ndarray
        Voltage angles in radians.
    iterations : int
    max_mismatch_pu : float
        Largest absolute mismatch at the final iteration.
    bus_types : tuple[BusType, ...]
        The (possibly PV→PQ-switched) bus types used in the final solve.
    """

    v_mag: np.ndarray
    v_ang: np.ndarray
    iterations: int
    max_mismatch_pu: float
    bus_types: tuple[BusType, ...]

    @property
    def v_complex(self) -> np.ndarray:
        """Complex voltage vector :math:`V\\,e^{j\\theta}`."""
        return self.v_mag * np.exp(1j * self.v_ang)


def _power_injections(v: np.ndarray, y_bus: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute :math:`P_i` and :math:`Q_i` from the complex voltages.

    :math:`S_i = V_i (\\sum_k Y_{ik} V_k)^*`.
    """
    s = v * np.conj(y_bus @ v)
    return s.real, s.imag


def _build_jacobian(
    v_mag: np.ndarray,
    v_ang: np.ndarray,
    y_bus: np.ndarray,
    p: np.ndarray,
    q: np.ndarray,
    pv_pq: np.ndarray,
    pq: np.ndarray,
) -> np.ndarray:
    """Build the polar NR Jacobian.

    The standard formulation (Grainger & Stevenson ch. 9; PPL-ALG-001
    Figure 4). Returns ``(m, m)`` where ``m = len(pv_pq) + len(pq)``.
    """
    n = len(v_mag)
    g = y_bus.real
    b = y_bus.imag

    vm = v_mag
    va = v_ang
    cos_ang = np.cos(va[:, None] - va[None, :])
    sin_ang = np.sin(va[:, None] - va[None, :])
    vv = vm[:, None] * vm[None, :]

    # Off-diagonal entries from the standard polar form; diagonals are
    # overwritten below (they have an additional self term).
    dp_dth = vv * (g * sin_ang - b * cos_ang)
    dp_dv = vm[:, None] * (g * cos_ang + b * sin_ang)
    dq_dth = -vv * (g * cos_ang + b * sin_ang)
    dq_dv = vm[:, None] * (g * sin_ang - b * cos_ang)

    idx = np.arange(n)
    dp_dth[idx, idx] = -q - np.diag(b) * vm * vm
    dp_dv[idx, idx] = p / vm + np.diag(g) * vm
    dq_dth[idx, idx] = p - np.diag(g) * vm * vm
    dq_dv[idx, idx] = q / vm - np.diag(b) * vm

    j11 = dp_dth[np.ix_(pv_pq, pv_pq)]
    j12 = dp_dv[np.ix_(pv_pq, pq)]
    j21 = dq_dth[np.ix_(pq, pv_pq)]
    j22 = dq_dv[np.ix_(pq, pq)]

    return np.block([[j11, j12], [j21, j22]])


def solve_powerflow(
    study: Study,
    branches: list[Branch],
    p_spec_pu: np.ndarray,
    q_spec_pu: np.ndarray,
    bus_types: tuple[BusType, ...],
    v_set_pu: np.ndarray,
    *,
    v_start: np.ndarray | None = None,
    ang_start: np.ndarray | None = None,
) -> PowerFlowSolution:
    r"""Solve the AC power flow for one snapshot.

    Parameters
    ----------
    study : Study
    branches : list[Branch]
        Branches in their current state (with temperature-updated R if
        called from the coupling loop).
    p_spec_pu, q_spec_pu : numpy.ndarray
        Specified net injections (generation − load) in per unit, one
        entry per bus. ``q_spec_pu`` is ignored at PV and slack buses.
    bus_types : tuple[BusType, ...]
        Role of each bus. Exactly one ``"slack"``.
    v_set_pu : numpy.ndarray
        Voltage set-points. Used at PV and slack buses, ignored at PQ.
    v_start, ang_start : numpy.ndarray, optional
        Warm-start voltage magnitudes and angles. Fall back to a flat
        start (v=v_set_pu for PV/slack else 1.0, θ=0).

    Returns
    -------
    PowerFlowSolution

    Raises
    ------
    PowerFlowDivergence
        If the mismatch does not fall below ``pf_tolerance_pu`` within
        ``pf_max_iter`` iterations, even after one retry from a flat
        start.
    """
    n = len(bus_types)
    types_list = list(bus_types)
    pv_pq = np.array([i for i, t in enumerate(types_list) if t in ("pv", "pq")], dtype=int)
    pq = np.array([i for i, t in enumerate(types_list) if t == "pq"], dtype=int)

    y_bus = build_ybus(n, branches)

    # Initial guess.
    if v_start is None:
        v_mag = np.where(np.array(types_list) == "pq", 1.0, v_set_pu)
        v_mag = np.asarray(v_mag, dtype=float)
    else:
        v_mag = v_start.copy()
        # Reapply |V| at PV/slack buses from their set-points.
        for i, t in enumerate(types_list):
            if t in ("pv", "slack"):
                v_mag[i] = v_set_pu[i]
    if ang_start is None:
        v_ang = np.zeros(n, dtype=float)
    else:
        v_ang = ang_start.copy()
        # Slack angle is always 0.
        slack = types_list.index("slack")
        v_ang -= v_ang[slack]

    tol = study.options.pf_tolerance_pu
    max_iter = study.options.pf_max_iter

    last_mismatch = float("inf")
    iteration = 0
    for retry in range(_MAX_RETRIES_FROM_FLAT + 1):
        for iteration in range(1, max_iter + 1):
            v = v_mag * np.exp(1j * v_ang)
            p_calc, q_calc = _power_injections(v, y_bus)

            dp = p_spec_pu - p_calc
            dq = q_spec_pu - q_calc

            mismatch_p = dp[pv_pq]
            mismatch_q = dq[pq]
            mismatch = np.concatenate([mismatch_p, mismatch_q])
            last_mismatch = float(np.max(np.abs(mismatch))) if mismatch.size else 0.0
            if last_mismatch < tol:
                return PowerFlowSolution(
                    v_mag=v_mag,
                    v_ang=v_ang,
                    iterations=iteration,
                    max_mismatch_pu=last_mismatch,
                    bus_types=tuple(types_list),
                )

            j = _build_jacobian(v_mag, v_ang, y_bus, p_calc, q_calc, pv_pq, pq)
            try:
                dx = np.linalg.solve(j, mismatch)
            except np.linalg.LinAlgError:
                break
            # Update
            n_ang = len(pv_pq)
            v_ang[pv_pq] += dx[:n_ang]
            if pq.size:
                v_mag[pq] += dx[n_ang:]

        # Did not converge on this attempt; try flat start once.
        if retry < _MAX_RETRIES_FROM_FLAT:
            _log.warning(
                "Power flow did not converge; retrying from a flat start.",
                iterations=iteration,
                max_mismatch_pu=last_mismatch,
            )
            v_mag = np.where(np.array(types_list) == "pq", 1.0, v_set_pu).astype(float)
            v_ang = np.zeros(n, dtype=float)

    raise PowerFlowDivergence(
        iterations=iteration,
        max_mismatch_pu=last_mismatch,
        bus_ids=(),
    )
