r"""Physical constants used throughout PyPowerlines.

This module is the single source of truth for the fundamental physical
constants needed by the transmission-line models. Every other module should
import constants from here rather than writing out literal values, so that:

* each value is defined, sourced and documented in exactly one place;
* a change of reference data (e.g. moving to a newer CODATA adjustment) is a
  one-line edit that propagates through the whole code base;
* reviewers can trace any number in a calculation back to its origin.

Conventions
-----------
* **Units** -- All values are in coherent SI units with no prefixes
  (metres, kilograms, seconds, amperes, kelvin). Callers are responsible for
  converting their inputs to SI before using these constants.
* **Types** -- Every constant is a plain built-in :class:`float` annotated
  as :data:`typing.Final`, so static type checkers (``mypy --strict``) will
  reject any attempt to rebind it.
* **Naming** -- Constants use ``UPPER_SNAKE_CASE`` per :pep:`8`. A trailing
  ``_0`` denotes a quantity defined for vacuum (free space).
* **Sources** -- Unless stated otherwise, values are taken from the CODATA
  2018 recommended values of the fundamental physical constants, published by
  NIST at https://physics.nist.gov/cuu/Constants/.
* **No logging, no runtime checks** -- This module only defines values. It
  has no behaviour to log and nothing that can fail at runtime. Correctness
  is enforced statically (``Final`` plus ``mypy``) and by the doctest below.

Constants overview
------------------
.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Name
     - Symbol
     - Unit
     - Main use in the code
   * - :data:`STEFAN_BOLTZMAN`
     - :math:`\sigma`
     - W m⁻² K⁻⁴
     - Radiative cooling of conductors (thermal rating)
   * - :data:`EPSILON_0`
     - :math:`\varepsilon_0`
     - F m⁻¹
     - Shunt capacitance / admittance
   * - :data:`MU_0`
     - :math:`\mu_0`
     - H m⁻¹
     - Series inductance / impedance

Notes
-----
Since the 2019 revision of the SI, the vacuum permeability :math:`\mu_0` is
no longer exactly :math:`4\pi \times 10^{-7}` H/m; it is now a measured
quantity (CODATA 2018: :math:`1.25663706212 \times 10^{-6}` H/m). The two
differ by about 5.5 parts in :math:`10^{10}`, which is many orders of
magnitude below the uncertainty of any engineering input (conductor geometry,
weather data, material properties). :data:`MU_0` deliberately keeps the
classical value because it is the one used in the standard closed-form line
parameter formulae (e.g. :math:`L = \frac{\mu_0}{2\pi}\ln\frac{D}{r'}`)
found in textbooks and utility reference data, which makes results easier to
cross-check by hand.

A consequence is that :data:`EPSILON_0` (a CODATA 2018 measured value) and
:data:`MU_0` (the classical value) do not satisfy
:math:`\varepsilon_0 \mu_0 c^2 = 1` to full double precision. The
discrepancy is of the same negligible order (~:math:`10^{-10}` relative) and
has no practical effect on power-system calculations.

Examples
--------
>>> from pypowerlines.constants import EPSILON_0, MU_0
>>> speed_of_light = 1.0 / (EPSILON_0 * MU_0) ** 0.5
>>> round(speed_of_light)
299792458
"""

from __future__ import annotations

import math
from typing import Final

__all__ = ["EPSILON_0", "MU_0", "STEFAN_BOLTZMAN"]


# ---------------------------------------------------------------------------
# Thermal constants
# ---------------------------------------------------------------------------

STEFAN_BOLTZMAN: Final[float] = 5.670374419e-8
r"""Stefan-Boltzmann constant :math:`\sigma` in W m⁻² K⁻⁴.

Relates the total power radiated per unit area by a black body to the fourth
power of its absolute temperature:

.. math::

    j^\star = \sigma T^4

In PyPowerlines it is used to compute the **radiative heat loss** of an
overhead conductor in the steady-state heat balance that determines its
thermal rating and operating temperature (as in IEEE Std 738 and CIGRE
TB 601):

.. math::

    q_r = \pi D \, \sigma \, \epsilon_s \left(T_s^4 - T_a^4\right)

where :math:`D` is the conductor diameter (m), :math:`\epsilon_s` its surface
emissivity, and :math:`T_s`, :math:`T_a` the conductor-surface and ambient
temperatures **in kelvin**.

:Value: :math:`5.670374419 \times 10^{-8}`
:Unit: W m⁻² K⁻⁴
:Source: CODATA 2018. Since the 2019 SI revision this is derived from exact
    constants (:math:`\sigma = 2\pi^5 k_B^4 / 15 h^3 c^2`), so it has no
    experimental uncertainty; the value shown is truncated to 10 significant
    figures as published by CODATA.

.. warning::
    Temperatures must be absolute (K), not °C. Because of the :math:`T^4`
    dependence, forgetting the 273.15 K offset produces wildly wrong results.

.. note::
    The identifier keeps the historical single-"n" spelling ``BOLTZMAN``.
    The physicist's name is spelled *Boltzmann*.
"""


# ---------------------------------------------------------------------------
# Electromagnetic constants
# ---------------------------------------------------------------------------

EPSILON_0: Final[float] = 8.8541878128e-12
r"""Vacuum (electric) permittivity :math:`\varepsilon_0` in F m⁻¹.

Describes how an electric field forms in free space. For overhead lines, air
is treated as having relative permittivity :math:`\varepsilon_r \approx 1`,
so :math:`\varepsilon_0` is used directly when computing the **shunt
capacitance** between conductors and to ground, e.g. for a single-phase
equivalent of a transposed three-phase line:

.. math::

    C = \frac{2\pi\varepsilon_0}{\ln\left(D_{eq} / r\right)}

The capacitance gives the line's shunt admittance
(:math:`Y = j\omega C` per unit length), which drives the line-charging
current and the Ferranti effect on lightly loaded lines.

:Value: :math:`8.8541878128 \times 10^{-12}`
:Unit: F m⁻¹ (equivalently C² N⁻¹ m⁻²)
:Source: CODATA 2018 (relative standard uncertainty :math:`1.5 \times 10^{-10}`).
"""

MU_0: Final[float] = 4e-7 * math.pi
r"""Vacuum (magnetic) permeability :math:`\mu_0` in H m⁻¹.

Describes how a magnetic field forms in free space. Overhead-line conductors
and the surrounding air are treated as non-magnetic
(:math:`\mu_r \approx 1`), so :math:`\mu_0` is used directly when computing
the **series inductance** of a line, e.g. for a single-phase equivalent of a
transposed three-phase line:

.. math::

    L = \frac{\mu_0}{2\pi} \ln\left(\frac{D_{eq}}{r'}\right)

where :math:`r' = r\,e^{-1/4}` is the geometric mean radius of a solid round
conductor. The inductance gives the series reactance
(:math:`X = \omega L` per unit length).

:Value: :math:`4\pi \times 10^{-7} \approx 1.2566370614 \times 10^{-6}`
:Unit: H m⁻¹ (equivalently N A⁻²)
:Source: Classical (pre-2019 SI) exact definition.

.. note::
    This is the *classical* value, not the CODATA 2018 measured value
    (:math:`1.25663706212 \times 10^{-6}` H/m). The difference is about
    :math:`5.5 \times 10^{-10}` relative and is irrelevant at engineering precision. See the
    module-level *Notes* section for the rationale.
"""
