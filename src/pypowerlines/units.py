"""Unit definitions and conversions.

PyPowerlines does all internal calculations in coherent SI base units
(volts, metres, ohms, ...). Engineering data, however, is almost always
given in "practical" units: system voltages in kV, conductor diameters in
mm, line impedances in Ω/km. This module provides the small, explicit helper
functions used to move between the two at the boundaries of the program.

Design rules
------------
* **Convert at the edges.** Inputs are converted to SI as soon as they are
  read (e.g. in :mod:`pypowerlines.io`), and results are converted back to
  practical units only when reported (e.g. in :mod:`pypowerlines.report`).
  Code in :mod:`pypowerlines.physics` and :mod:`pypowerlines.solver` should
  only ever see SI values.
* **One function per direction.** Every conversion has an explicit inverse
  (``a_to_b`` / ``b_to_a``) so the direction is visible at the call site,
  instead of a bare ``* 1e3`` whose meaning the reader has to guess.
* **Pure and scalar.** The functions have no side effects and take and
  return plain :class:`float` values. Because they only use ``*``, they also
  work element-wise on :class:`numpy.ndarray` inputs at runtime, although
  the type hints only promise :class:`float`.
* **Linear, scale-only.** Every conversion here is a pure scale factor
  (no offset), so each function is exactly undone by its inverse up to
  floating-point rounding.
* **No logging, no validation.** These functions run inside hot loops
  (every span, every hour), and PPL-ADR-001 forbids logging there. They
  also accept any value, including negatives and NaN, because whether a
  value is *allowed* depends on what it is (a negative voltage angle is
  fine, a negative conductor diameter is not). Range checks belong in input
  validation (rule V-007), which reports them as an
  :class:`~pypowerlines.errors.InputError`.

Function overview
-----------------
.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - Quantity
     - Practical -> SI
     - SI -> practical
   * - Voltage (kV <-> V)
     - :func:`kv_to_v`
     - :func:`v_to_kv`
   * - Length (mm <-> m)
     - :func:`mm_to_m`
     - :func:`m_to_mm`
   * - Impedance per unit length (Ω/km <-> Ω/m)
     - :func:`ohm_per_km_to_ohm_per_m`
     - :func:`ohm_per_m_to_ohm_per_km`

See Also
--------
pypowerlines.constants : Physical constants, all stored in SI units.

Notes
-----
Conversions multiply by a decimal factor such as ``1e-3``. Neither
``0.001`` nor most decimal inputs are exactly representable in binary
floating point, so results may differ from the "obvious" decimal answer in
the last digit (about 1 part in :math:`10^{16}`). This is far below the
accuracy of any engineering input and can be ignored, but it means results
should be compared with a tolerance (e.g. :func:`math.isclose`), not ``==``.

Examples
--------
Convert a 400 kV line voltage and a 28 mm conductor diameter to SI:

>>> from pypowerlines.units import kv_to_v, mm_to_m
>>> kv_to_v(400.0)
400000.0
>>> mm_to_m(28.0)
0.028
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "kv_to_v",
    "m_to_mm",
    "mm_to_m",
    "ohm_per_km_to_ohm_per_m",
    "ohm_per_m_to_ohm_per_km",
    "v_to_kv",
]


# ---------------------------------------------------------------------------
# SI prefix factors
# ---------------------------------------------------------------------------
# Named so that each conversion below reads as "value times prefix" rather
# than containing a magic number. Private: callers should use the functions.

_KILO: Final[float] = 1e3
"""SI prefix *kilo* (k), :math:`10^{3}`."""

_MILLI: Final[float] = 1e-3
"""SI prefix *milli* (m), :math:`10^{-3}`."""


# ---------------------------------------------------------------------------
# Voltage
# ---------------------------------------------------------------------------


def kv_to_v(kv: float) -> float:
    """Convert a voltage from kilovolts (kV) to volts (V).

    Transmission voltages are normally quoted in kV (e.g. 132, 275, 400 kV),
    but the physics and solver code works in volts.

    Parameters
    ----------
    kv : float
        Voltage in kilovolts.

    Returns
    -------
    float
        The same voltage in volts, ``kv * 1e3``.

    See Also
    --------
    v_to_kv : The inverse conversion.

    Examples
    --------
    >>> kv_to_v(400.0)
    400000.0
    """
    return kv * _KILO


def v_to_kv(v: float) -> float:
    """Convert a voltage from volts (V) to kilovolts (kV).

    Used mainly when reporting results back to the user in practical units.

    Parameters
    ----------
    v : float
        Voltage in volts.

    Returns
    -------
    float
        The same voltage in kilovolts, ``v * 1e-3``.

    See Also
    --------
    kv_to_v : The inverse conversion.

    Examples
    --------
    >>> v_to_kv(275000.0)
    275.0
    """
    return v * _MILLI


# ---------------------------------------------------------------------------
# Length
# ---------------------------------------------------------------------------


def mm_to_m(mm: float) -> float:
    """Convert a length from millimetres (mm) to metres (m).

    Conductor diameters, strand diameters and radii are usually given in mm
    in manufacturer datasheets; the geometry and thermal models need metres.

    Parameters
    ----------
    mm : float
        Length in millimetres.

    Returns
    -------
    float
        The same length in metres, ``mm * 1e-3``.

    See Also
    --------
    m_to_mm : The inverse conversion.

    Examples
    --------
    >>> mm_to_m(28.0)
    0.028
    """
    return mm * _MILLI


def m_to_mm(m: float) -> float:
    """Convert a length from metres (m) to millimetres (mm).

    Parameters
    ----------
    m : float
        Length in metres.

    Returns
    -------
    float
        The same length in millimetres, ``m * 1e3``.

    See Also
    --------
    mm_to_m : The inverse conversion.

    Examples
    --------
    >>> m_to_mm(0.5)
    500.0
    """
    return m * _KILO


# ---------------------------------------------------------------------------
# Impedance per unit length
# ---------------------------------------------------------------------------
# Line parameters (R, X, and similarly per-length quantities) are quoted per
# kilometre in datasheets and network data, but are per metre in SI.
# Note the factors run the "opposite" way to the length conversions: a
# kilometre is 1000 m, so a value *per* km is 1000 times smaller per m.


def ohm_per_km_to_ohm_per_m(ohm_per_km: float) -> float:
    """Convert an impedance per unit length from Ω/km to Ω/m.

    Works the same way for resistance, reactance or impedance magnitude,
    since all are measured in ohms.

    Parameters
    ----------
    ohm_per_km : float
        Impedance per unit length in ohms per kilometre.

    Returns
    -------
    float
        The same quantity in ohms per metre, ``ohm_per_km * 1e-3``.

    See Also
    --------
    ohm_per_m_to_ohm_per_km : The inverse conversion.

    Examples
    --------
    >>> ohm_per_km_to_ohm_per_m(250.0)
    0.25
    """
    return ohm_per_km * _MILLI


def ohm_per_m_to_ohm_per_km(ohm_per_m: float) -> float:
    """Convert an impedance per unit length from Ω/m to Ω/km.

    Parameters
    ----------
    ohm_per_m : float
        Impedance per unit length in ohms per metre.

    Returns
    -------
    float
        The same quantity in ohms per kilometre, ``ohm_per_m * 1e3``.

    See Also
    --------
    ohm_per_km_to_ohm_per_m : The inverse conversion.

    Examples
    --------
    >>> ohm_per_m_to_ohm_per_km(0.25)
    250.0
    """
    return ohm_per_m * _KILO
