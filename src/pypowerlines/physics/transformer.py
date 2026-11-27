"""Two-winding transformer physics: equivalent admittance and losses.

For a positive-sequence AC power flow a two-winding transformer is
represented by its series impedance (:math:`Z = R + jX`) referred to a
chosen side and a tap ratio on the "from" (HV) side (PPL-ALG-001 section
2). Losses are a side result:

* no-load (iron) loss scales with voltage squared (CS-20);
* load (copper) loss scales with apparent-power squared.
"""

from __future__ import annotations

from pypowerlines.model import TransformerType

__all__ = ["loss_mw", "series_impedance_pu", "tap_ratio"]


# ---------------------------------------------------------------------------
# Per-unit impedance (CS-02, CS-20)
# ---------------------------------------------------------------------------


def series_impedance_pu(transformer_type: TransformerType, base_mva: float) -> complex:
    r"""Series impedance of one transformer unit, in per unit on the system base.

    Change of base from the transformer's own ``z_pct`` (on its own MVA
    base) to the system ``base_mva``:

    .. math::

        Z_{pu,\text{sys}} = (z_\%/100) \cdot (S_\text{sys} / S_\text{xfmr})

    split into R and X by ``x_over_r``.

    Parameters
    ----------
    transformer_type : TransformerType
    base_mva : float
        System MVA base used for the power flow.

    Returns
    -------
    complex
        ``R + jX`` in per unit on the system base.
    """
    z_mag = (transformer_type.z_pct / 100.0) * (base_mva / transformer_type.rating_mva)
    x_over_r = max(transformer_type.x_over_r, 1e-6)
    x = z_mag / (1.0 + 1.0 / (x_over_r * x_over_r)) ** 0.5
    r = x / x_over_r
    return complex(r, x)


def tap_ratio(transformer_type: TransformerType, tap_pos: int) -> float:
    r"""Off-nominal HV/LV ratio from the tap position.

    The tap step is quoted in % per step; tap position 0 is nominal. By
    convention this is the HV-side multiplier (PPL-ALG-001 section 2):
    ``t = 1 + tap_pos * step/100``.

    Parameters
    ----------
    transformer_type : TransformerType
    tap_pos : int
        Tap position (bounded by ``[tap_min, tap_max]``).

    Returns
    -------
    float
        Dimensionless ratio ``t``.
    """
    return 1.0 + tap_pos * transformer_type.tap_step_pct / 100.0


# ---------------------------------------------------------------------------
# Losses (CS-20)
# ---------------------------------------------------------------------------


def loss_mw(
    transformer_type: TransformerType,
    count: int,
    s_mva: float,
    v_pu: float = 1.0,
) -> float:
    r"""Total transformer losses at a given loading, MW.

    .. math::

        P_\text{nl} = P_0 (V/V_r)^2, \quad P_\text{ll} = P_k (S/S_r)^2

    A transformer *bank* of ``count`` identical units shares the apparent
    power equally, so each unit carries :math:`S / n` and its load loss is
    scaled accordingly; no-load loss adds up across all ``count`` units.

    Parameters
    ----------
    transformer_type : TransformerType
    count : int
        Number of parallel identical units.
    s_mva : float
        Total apparent power flowing through the bank, MVA.
    v_pu : float, default 1.0
        Voltage magnitude on the regulated side, per unit of nominal.

    Returns
    -------
    float
        Total losses in megawatts.
    """
    s_per_unit = s_mva / max(count, 1)
    p0_total = transformer_type.p0_kw * count * v_pu * v_pu
    pk_total = transformer_type.pk_kw * count * (s_per_unit / transformer_type.rating_mva) ** 2
    return (p0_total + pk_total) * 1e-3
