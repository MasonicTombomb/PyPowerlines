"""Equipment library: conductor, tower and transformer catalogues.

The library is a lookup from a short name (``"ACSR Zebra"``,
``"L6_400kV"``, ``"SGT_240MVA_400_132"``) to a frozen
:class:`~pypowerlines.model.ConductorType`,
:class:`~pypowerlines.model.TowerType` or
:class:`~pypowerlines.model.TransformerType`. PyPowerlines ships with a
small built-in library of common UK transmission equipment, which can be
extended or overridden by loading user YAML files on top of it.

The IO module uses this lookup during validation to turn the library
names on spans and transformers into the real objects (PPL-DATA-001
section 7).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from pypowerlines.model import ConductorType, TowerType, TransformerType

__all__ = ["Library", "builtin_library"]


# ---------------------------------------------------------------------------
# Built-in equipment
# ---------------------------------------------------------------------------
# All values in SI; mm and kN inputs from datasheets converted here. Data
# from PPL-CH-001 (ACSR Zebra) and PPL-REF-001 (tower and transformer).

_ACSR_ZEBRA = ConductorType(
    name="ACSR Zebra",
    diameter_m=28.62e-3,
    r20_ohm_per_m=0.0674e-3,  # 0.0674 Ω/km
    alpha_per_k=0.00403,
    sub_conductors=2,
    bundle_spacing_m=0.4,
    absorptivity=0.8,
    emissivity=0.7,
    t_max_c=75.0,
    mass_kg_per_m=1.621,
    uts_kn=131.9,
)
"""Twin ACSR Zebra, as used on the North Wales reference network.

The ``sub_conductors`` and ``bundle_spacing_m`` defaults describe the
standard 400 kV twin bundle; a single-conductor variant can be made with
``replace(ACSR_ZEBRA, sub_conductors=1, bundle_spacing_m=0.0)``.
"""


_L6_400KV = TowerType(
    name="L6_400kV",
    # Three phases flat, 11 m apart, as in PPL-REF-001 section 7 and the
    # PPL-CH-001 CS-08 worked example. Height is not used by the current
    # positive-sequence model, so it is noted only for documentation.
    phases_m=((-11.0, 25.0), (0.0, 25.0), (11.0, 25.0)),
    earth_wires_m=(),
)
"""L6 standard UK 400 kV tower, flat phase arrangement, 11 m spacing."""


_SGT_240MVA_400_132 = TransformerType(
    name="SGT_240MVA_400_132",
    rating_mva=240.0,
    hv_kv=400.0,
    lv_kv=132.0,
    z_pct=15.0,
    x_over_r=40.0,
    p0_kw=150.0,  # typical no-load loss
    pk_kw=700.0,  # per PPL-REF-001 Table 3
    tap_step_pct=1.25,
    tap_min=-10,
    tap_max=10,
)
"""Standard UK 400/132 kV SGT, 240 MVA per unit."""


_BUILTIN_CONDUCTORS: tuple[ConductorType, ...] = (
    _ACSR_ZEBRA,
    # Single-conductor variants, handy for small test networks.
    replace(_ACSR_ZEBRA, name="ACSR Zebra x1", sub_conductors=1, bundle_spacing_m=0.0),
)
_BUILTIN_TOWERS: tuple[TowerType, ...] = (_L6_400KV,)
_BUILTIN_TRANSFORMERS: tuple[TransformerType, ...] = (_SGT_240MVA_400_132,)


# ---------------------------------------------------------------------------
# Library class
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Library:
    """Named catalogues of equipment types.

    Three independent dictionaries keyed by library name. The lookup is
    case-sensitive and must match the names used in the grid file exactly.

    Parameters
    ----------
    conductors, towers, transformers : Mapping[str, ...]
        Equipment catalogues keyed by name. The constructor copies each
        mapping into an internal dict.
    """

    conductors: Mapping[str, ConductorType] = field(default_factory=dict)
    towers: Mapping[str, TowerType] = field(default_factory=dict)
    transformers: Mapping[str, TransformerType] = field(default_factory=dict)

    def get_conductor(self, name: str) -> ConductorType:
        """Return the named conductor type.

        Parameters
        ----------
        name : str
            Library key.

        Returns
        -------
        ConductorType

        Raises
        ------
        KeyError
            If ``name`` is not in the library.
        """
        return self.conductors[name]

    def get_tower(self, name: str) -> TowerType:
        """Return the named tower type (see :meth:`get_conductor`)."""
        return self.towers[name]

    def get_transformer(self, name: str) -> TransformerType:
        """Return the named transformer type (see :meth:`get_conductor`)."""
        return self.transformers[name]

    def merged_with(self, other: Library) -> Library:
        """Return a new library that overlays ``other`` on top of this one.

        User libraries override the built-in catalogue entry by entry
        (PPL-UG-001 section 8 FAQ "Where do conductor properties come
        from?").

        Parameters
        ----------
        other : Library
            Library whose entries take precedence.

        Returns
        -------
        Library
            New instance with the merged catalogues.
        """
        return Library(
            conductors={**self.conductors, **other.conductors},
            towers={**self.towers, **other.towers},
            transformers={**self.transformers, **other.transformers},
        )


def builtin_library() -> Library:
    """Return a copy of the built-in library.

    Called by the loader before overlaying any user YAML libraries. Each
    call returns a fresh object so callers may safely mutate it before
    use (although mutation after validation is discouraged).

    Returns
    -------
    Library
        Catalogue of ACSR Zebra, ``L6_400kV`` tower and
        ``SGT_240MVA_400_132`` transformer.

    Examples
    --------
    >>> lib = builtin_library()
    >>> lib.get_conductor("ACSR Zebra").r20_ohm_per_m
    6.74e-05
    """
    return Library(
        conductors={c.name: c for c in _BUILTIN_CONDUCTORS},
        towers={t.name: t for t in _BUILTIN_TOWERS},
        transformers={t.name: t for t in _BUILTIN_TRANSFORMERS},
    )
