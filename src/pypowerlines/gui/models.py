"""Qt table models that wrap :class:`SnapshotResult` collections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

if TYPE_CHECKING:
    from pypowerlines.model import SnapshotResult


@dataclass(frozen=True)
class _Column:
    """One column definition for a results table."""

    header: str
    attr: str
    fmt: str = "{}"


_BUS_COLUMNS = (
    _Column("Bus", "bus_id"),
    _Column("V (pu)", "v_pu", "{:.4f}"),
    _Column("Angle (°)", "angle_deg", "{:.3f}"),
    _Column("P inj (MW)", "p_inj_mw", "{:.2f}"),
    _Column("Q inj (MVAr)", "q_inj_mvar", "{:.2f}"),
)
_BRANCH_COLUMNS = (
    _Column("Branch", "branch_id"),
    _Column("Kind", "kind"),
    _Column("From", "from_bus"),
    _Column("To", "to_bus"),
    _Column("P from (MW)", "p_from_mw", "{:.2f}"),
    _Column("Q from (MVAr)", "q_from_mvar", "{:.2f}"),
    _Column("I (A)", "i_a", "{:.0f}"),
    _Column("Loss (MW)", "loss_mw", "{:.3f}"),
    _Column("Loading (%)", "loading_pct", "{:.1f}"),
)
_CONDUCTOR_COLUMNS = (
    _Column("Line", "line_id"),
    _Column("Zone", "zone_id"),
    _Column("T (°C)", "t_c", "{:.1f}"),
    _Column("Ampacity (A)", "ampacity_a", "{:.0f}"),
    _Column("Q joule (W/m)", "q_joule_wpm", "{:.2f}"),
    _Column("Q solar (W/m)", "q_solar_wpm", "{:.2f}"),
    _Column("Q conv (W/m)", "q_conv_wpm", "{:.2f}"),
    _Column("Q rad (W/m)", "q_rad_wpm", "{:.2f}"),
    _Column("Overload", "overload"),
)
_TRANSFORMER_COLUMNS = (
    _Column("Transformer", "transformer_id"),
    _Column("S (MVA)", "s_mva", "{:.1f}"),
    _Column("P0 (kW)", "p0_kw", "{:.1f}"),
    _Column("Pk (kW)", "pk_kw", "{:.1f}"),
    _Column("Loss (MW)", "loss_mw", "{:.3f}"),
)


class _RowsModel(QAbstractTableModel):
    """Table model backed by a list of row objects and a column schema."""

    def __init__(self, columns: tuple[_Column, ...]) -> None:
        super().__init__()
        self._columns = columns
        self._rows: list[object] = []

    def set_rows(self, rows: list[object]) -> None:
        """Replace all rows and emit the reset signal."""
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(self._columns)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section].header
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return None
        row = self._rows[index.row()]
        col = self._columns[index.column()]
        value = getattr(row, col.attr, None)
        if value is None:
            return ""
        if isinstance(value, float):
            return col.fmt.format(value)
        return str(value)


def bus_model() -> _RowsModel:
    """Return an empty bus-results table model."""
    return _RowsModel(_BUS_COLUMNS)


def branch_model() -> _RowsModel:
    """Return an empty branch-results table model."""
    return _RowsModel(_BRANCH_COLUMNS)


def conductor_model() -> _RowsModel:
    """Return an empty conductor-results table model."""
    return _RowsModel(_CONDUCTOR_COLUMNS)


def transformer_model() -> _RowsModel:
    """Return an empty transformer-results table model."""
    return _RowsModel(_TRANSFORMER_COLUMNS)


def populate_from_result(
    *,
    buses: _RowsModel,
    branches: _RowsModel,
    conductors: _RowsModel,
    transformers: _RowsModel,
    result: SnapshotResult,
) -> None:
    """Load a solved snapshot into the four table models."""
    buses.set_rows(list(result.buses))
    branches.set_rows(list(result.branches))
    cond_rows: list[object] = []
    for br in result.branches:
        cond_rows.extend(br.conductors)
    conductors.set_rows(cond_rows)
    transformers.set_rows(list(result.transformers))
