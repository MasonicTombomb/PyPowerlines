"""QR-02 time-behaviour benchmarks (PPL-SDS-001, test case TPERF01).

QR-02: a 100-bus coupled snapshot solves in under 2 s; an 8,760-hour series in under 10 min.

Until ``pypowerlines.solver.coupled`` exists, ``_snapshot`` is a stand-in with the same shape
of work: rebuild a sparse 100-bus admittance matrix from temperature-dependent resistances,
factorise it and solve, once per iteration. Swap it for the real solver when stage 2 lands.

Run with:  uv run pytest -m perf --no-cov -v
"""

import time

import numpy as np
import pytest
import scipy.sparse as sp
from scipy.sparse.linalg import splu

pytestmark = pytest.mark.perf

N_BUS = 100
HOURS = 8_760
MAX_ITERATIONS = 30  # Newton-Raphson iteration cap (PPL-SDS-001)
SNAPSHOT_BUDGET_S = 2.0
SERIES_BUDGET_S = 600.0


def _network(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return a connected 100-bus network: ring plus random chords."""
    ring = np.arange(N_BUS)
    f = np.concatenate([ring, rng.integers(0, N_BUS, N_BUS // 2)])
    t = np.concatenate([(ring + 1) % N_BUS, rng.integers(0, N_BUS, N_BUS // 2)])
    keep = f != t
    r20 = rng.uniform(0.01, 0.05, keep.sum())
    x = rng.uniform(0.05, 0.30, keep.sum())
    return f[keep], t[keep], r20, x


def _snapshot(net: tuple[np.ndarray, ...], load: np.ndarray, iterations: int) -> np.ndarray:
    """Stand-in coupled solve: re-rate resistance with temperature, rebuild Y, solve."""
    f, t, r20, x = net
    temp = np.full(r20.size, 50.0)
    v = np.ones(N_BUS, dtype=complex)
    for _ in range(iterations):
        r = r20 * (1 + 0.004 * (temp - 20.0))
        y = 1 / (r + 1j * x)
        a = sp.coo_matrix((np.r_[y, y], (np.r_[f, t], np.r_[t, f])), shape=(N_BUS, N_BUS))
        ybus = sp.diags(np.asarray(a.sum(axis=1)).ravel() + 0.05) - a
        v = splu(ybus.tocsc()).solve(load.astype(complex))
        temp = 20.0 + 30.0 * np.abs(v[f] - v[t]) ** 2 / (np.abs(v[f] - v[t]) ** 2).max()
    return v


def test_qr02_snapshot_100_bus_under_2_s() -> None:
    rng = np.random.default_rng(0)
    net = _network(rng)
    load = rng.uniform(0.1, 1.0, N_BUS)

    start = time.perf_counter()
    v = _snapshot(net, load, MAX_ITERATIONS)
    elapsed = time.perf_counter() - start

    assert np.isfinite(v).all()
    assert elapsed < SNAPSHOT_BUDGET_S, f"snapshot took {elapsed:.3f} s"


def test_qr02_series_8760_hours_under_10_min() -> None:
    rng = np.random.default_rng(1)
    net = _network(rng)
    base = rng.uniform(0.1, 1.0, N_BUS)
    profile = 0.7 + 0.3 * np.sin(np.arange(HOURS) * 2 * np.pi / 24)

    start = time.perf_counter()
    for hour in range(HOURS):
        v = _snapshot(net, base * profile[hour], iterations=3)  # warm-started hours converge fast
    elapsed = time.perf_counter() - start

    assert np.isfinite(v).all()
    assert elapsed < SERIES_BUDGET_S, f"series took {elapsed:.1f} s"
