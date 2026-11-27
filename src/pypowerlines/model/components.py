"""Network components: buses, lines, transformers, loads, generators.

These classes are the "nouns" of a study. They are frozen dataclasses so
that the solver can rely on an immutable grid (PPL-SDS-001 section 5.4).

Library types (:class:`ConductorType`, :class:`TowerType`,
:class:`TransformerType`) carry the equipment data resolved from the
component library. Network objects (:class:`Bus`, :class:`Line`,
:class:`Transformer`, :class:`Load`, :class:`Generator`,
:class:`WeatherZone`) are composed by the :class:`Grid` tree owned by the
study.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "Bus",
    "BusType",
    "ConductorType",
    "Generator",
    "Grid",
    "Line",
    "Load",
    "Span",
    "TowerType",
    "Transformer",
    "TransformerType",
    "WeatherZone",
]


BusType = Literal["slack", "pv", "pq"]
"""Bus role in the power flow (PPL-DATA-001 Table 3).

* ``"slack"`` -- balances the network; its voltage is fixed in magnitude
  and angle (angle reference = 0).
* ``"pv"`` -- generator bus holding a voltage magnitude set-point; P is
  specified.
* ``"pq"`` -- load bus with specified P and Q injections.
"""


# ---------------------------------------------------------------------------
# Library types (equipment data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConductorType:
    """One conductor as it appears in the component library.

    Fields match PPL-DATA-001 Table 6 and the worked examples of
    PPL-CH-001 (CS-04 to CS-15).

    Parameters
    ----------
    name : str
        Library key, e.g. ``"ACSR Zebra"``.
    diameter_m : float
        Overall conductor diameter in metres.
    r20_ohm_per_m : float
        DC resistance per metre at 20 °C.
    alpha_per_k : float, default 0.00403
        Temperature coefficient of resistance, K⁻¹ (aluminium default).
    sub_conductors : int, default 1
        Number of sub-conductors in a bundle. ``>1`` means a bundle.
    bundle_spacing_m : float, default 0.0
        Spacing between adjacent sub-conductors. Required when
        ``sub_conductors > 1``.
    absorptivity, emissivity : float, default 0.8 / 0.7
        Dimensionless surface properties used by IEEE 738.
    t_max_c : float, default 75.0
        Maximum allowed conductor temperature in °C (used for ampacity).
    mass_kg_per_m : float, default 0.0
        Total mass per metre; needed only for transient heating / sag.
    uts_kn : float, default 0.0
        Ultimate tensile strength; needed only for sag.
    """

    name: str
    diameter_m: float
    r20_ohm_per_m: float
    alpha_per_k: float = 0.00403
    sub_conductors: int = 1
    bundle_spacing_m: float = 0.0
    absorptivity: float = 0.8
    emissivity: float = 0.7
    t_max_c: float = 75.0
    mass_kg_per_m: float = 0.0
    uts_kn: float = 0.0


@dataclass(frozen=True, slots=True)
class TowerType:
    """Tower geometry used to compute line parameters.

    Parameters
    ----------
    name : str
        Library key, e.g. ``"L6_400kV"``.
    phases_m : tuple[tuple[float, float], ...]
        ``(x, y)`` coordinates of each phase conductor centre, metres.
        Three per circuit; if more than three are given PyPowerlines takes
        the first three as the positive-sequence reference and treats the
        extras as earth wires for future zero-sequence work.
    earth_wires_m : tuple[tuple[float, float], ...]
        ``(x, y)`` coordinates of earth wires (optional).
    """

    name: str
    phases_m: tuple[tuple[float, float], ...]
    earth_wires_m: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class TransformerType:
    """Two-winding transformer as it appears in the component library.

    Fields match PPL-DATA-001 Table 7 and PPL-CH-001 CS-20.

    Parameters
    ----------
    name : str
        Library key.
    rating_mva : float
        Rated apparent power (nameplate) per unit, MVA.
    hv_kv, lv_kv : float
        Nominal HV/LV line-to-line voltages, kV.
    z_pct : float
        Short-circuit impedance on the transformer's own base, %.
    x_over_r : float, default 40
        Reactance-to-resistance ratio of the series impedance.
    p0_kw : float, default 0
        No-load (iron) loss at rated voltage, kW.
    pk_kw : float, default 0
        Load (copper) loss at rated current, kW.
    tap_step_pct : float, default 1.25
        Tap step on the HV side, % per step.
    tap_min, tap_max : int, default -10 / +10
        Tap position limits (0 = nominal).
    """

    name: str
    rating_mva: float
    hv_kv: float
    lv_kv: float
    z_pct: float
    x_over_r: float = 40.0
    p0_kw: float = 0.0
    pk_kw: float = 0.0
    tap_step_pct: float = 1.25
    tap_min: int = -10
    tap_max: int = 10


# ---------------------------------------------------------------------------
# Network objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WeatherZone:
    """A group of spans that share the same environmental inputs.

    Parameters
    ----------
    id : str
        Unique zone identifier.
    name : str
        Human-readable name.
    latitude_deg : float
        Latitude in degrees (positive north). Used for solar position.
    elevation_m : float, default 0.0
        Mean elevation above sea level, metres.
    temperature_offset_k : float, default 0.0
        Offset added to the scenario's base ambient temperature to model
        local effects such as upland cooling.
    wind_multiplier : float, default 1.0
        Factor applied to the scenario's base wind speed.
    """

    id: str
    name: str
    latitude_deg: float
    elevation_m: float = 0.0
    temperature_offset_k: float = 0.0
    wind_multiplier: float = 1.0


@dataclass(frozen=True, slots=True)
class Bus:
    """A node of the network at one nominal voltage.

    Parameters
    ----------
    id : str
        Unique identifier, matches PPL-DATA-001 rule for IDs.
    name : str
        Human-readable name.
    kv : float
        Nominal line-to-line voltage, kV.
    type : {"slack", "pv", "pq"}
        Bus role in the power flow.
    v_set_pu : float, default 1.0
        Voltage set-point magnitude (per unit) for PV and slack buses.
        Ignored for PQ buses.
    lat, lon : float, optional
        Geographic coordinates, for maps.
    """

    id: str
    name: str
    kv: float
    type: BusType
    v_set_pu: float = 1.0
    lat: float | None = None
    lon: float | None = None


@dataclass(frozen=True, slots=True)
class Span:
    """A section of line between two adjacent towers.

    A line is a list of spans; spans in different weather zones have
    different conductor temperatures even on the same line.

    Parameters
    ----------
    length_m : float
        Span length in metres.
    tower : TowerType
        Tower geometry (library reference resolved at load time).
    conductor : ConductorType
        Conductor properties (library reference resolved at load time).
    zone : WeatherZone
        Weather zone this span belongs to.
    elevation_m : float, optional
        Local elevation above sea level; falls back to the zone value.
    azimuth_deg : float, optional
        Bearing of the span (degrees from north), for the wind-angle
        factor in IEEE 738. If ``None``, wind is treated as perpendicular.
    """

    length_m: float
    tower: TowerType
    conductor: ConductorType
    zone: WeatherZone
    elevation_m: float | None = None
    azimuth_deg: float | None = None


@dataclass(frozen=True, slots=True)
class Line:
    """An overhead transmission line between two buses.

    Parameters
    ----------
    id : str
        Unique identifier.
    from_bus, to_bus : Bus
        End buses (resolved at load time; both must have the same kV).
    circuits : int, default 1
        Number of parallel identical circuits on the same tower route.
        The series impedance is divided by ``circuits`` and the shunt
        susceptance is multiplied.
    spans : tuple[Span, ...]
        Spans that make up the line, in order. At least one.
    """

    id: str
    from_bus: Bus
    to_bus: Bus
    circuits: int
    spans: tuple[Span, ...]

    @property
    def length_m(self) -> float:
        """Total line length as the sum of its span lengths."""
        return sum(s.length_m for s in self.spans)


@dataclass(frozen=True, slots=True)
class Transformer:
    """A two-winding power transformer between an HV and an LV bus.

    Parameters
    ----------
    id : str
        Unique identifier.
    hv_bus, lv_bus : Bus
        End buses (resolved at load time).
    type : TransformerType
        Nameplate data from the library.
    count : int, default 1
        Number of identical parallel units. Multiplies the equivalent
        admittance and divides the equivalent series impedance.
    tap_pos : int, default 0
        Tap position; 0 is nominal.
    """

    id: str
    hv_bus: Bus
    lv_bus: Bus
    type: TransformerType
    count: int = 1
    tap_pos: int = 0


@dataclass(frozen=True, slots=True)
class Load:
    """Constant power load connected to a bus.

    Parameters
    ----------
    id : str
        Unique identifier.
    bus : Bus
        Bus the load connects to.
    p_mw, q_mvar : float
        Active and reactive power drawn, MW / Mvar. Positive values are
        consumed power (standard power-system sign convention).
    """

    id: str
    bus: Bus
    p_mw: float
    q_mvar: float


@dataclass(frozen=True, slots=True)
class Generator:
    """A generator attached to a bus (PV or slack).

    Parameters
    ----------
    id : str
        Unique identifier.
    bus : Bus
        Bus the generator connects to. Determines whether it is PV or
        slack via :attr:`Bus.type`.
    p_mw : float
        Scheduled active power output, MW. Ignored for slack.
    v_set_pu : float
        Voltage magnitude set-point. Ignored if the bus already specifies
        one at a higher level.
    q_min_mvar, q_max_mvar : float
        Reactive-power limits. Unlimited by default (``±inf``).
    """

    id: str
    bus: Bus
    p_mw: float
    v_set_pu: float = 1.0
    q_min_mvar: float = float("-inf")
    q_max_mvar: float = float("inf")


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Grid:
    """The whole validated network: buses, branches, loads, generators.

    Owned by :class:`~pypowerlines.model.Study`. All collections are tuples
    so the object stays hashable-shaped and callers cannot mutate them.

    Parameters
    ----------
    buses, lines, transformers, loads, generators, zones : tuple
        Network objects, ordered as they appeared in the input file.
    """

    buses: tuple[Bus, ...]
    lines: tuple[Line, ...]
    transformers: tuple[Transformer, ...]
    loads: tuple[Load, ...]
    generators: tuple[Generator, ...]
    zones: tuple[WeatherZone, ...] = field(default_factory=tuple)

    def bus_index(self) -> dict[str, int]:
        """Return the ``{bus_id: row/column index}`` mapping used in the Y-bus."""
        return {bus.id: i for i, bus in enumerate(self.buses)}

    def bus_by_id(self, bus_id: str) -> Bus:
        """Return the bus with the given id.

        Parameters
        ----------
        bus_id : str
            Bus identifier.

        Returns
        -------
        Bus

        Raises
        ------
        KeyError
            If no bus with that id exists in this grid.
        """
        for bus in self.buses:
            if bus.id == bus_id:
                return bus
        raise KeyError(bus_id)
