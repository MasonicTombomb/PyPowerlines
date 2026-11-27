"""Network diagram for the workbench.

A ``QGraphicsView`` showing buses as nodes and branches as edges, with
line colour reflecting branch loading when a solved snapshot is loaded.
Bus coordinates come from a small Fruchterman-Reingold spring layout so
the widget works for any grid, not just the shipped example.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

if TYPE_CHECKING:
    from pypowerlines.model import Grid, SnapshotResult, Study

_BUS_RADIUS = 14.0
_NODE_SIZE = _BUS_RADIUS * 2
_CANVAS = 600.0  # nominal half-width of the layout bounding box in scene units
# Loading percentage thresholds for the traffic-light colouring.
_LOADING_GREEN_MAX = 60.0
_LOADING_AMBER_MAX = 85.0
_LOADING_ORANGE_MAX = 100.0
# HV threshold for node colour (kV).
_HV_BUS_KV = 275.0


@dataclass(frozen=True)
class _Edge:
    """Edge for layout: unordered bus pair."""

    a: str
    b: str


def _collect_edges(grid: Grid) -> list[_Edge]:
    edges: list[_Edge] = []
    for line in grid.lines:
        edges.append(_Edge(line.from_bus.id, line.to_bus.id))
    for tx in grid.transformers:
        edges.append(_Edge(tx.hv_bus.id, tx.lv_bus.id))
    return edges


def _spring_layout(
    bus_ids: list[str],
    edges: list[_Edge],
    *,
    iterations: int = 300,
    seed: int = 0,
) -> dict[str, tuple[float, float]]:
    """Fruchterman-Reingold layout. Deterministic for a fixed seed."""
    rng = random.Random(seed)
    n = len(bus_ids)
    if n == 0:
        return {}
    pos: dict[str, list[float]] = {
        b: [rng.uniform(-_CANVAS, _CANVAS), rng.uniform(-_CANVAS, _CANVAS)] for b in bus_ids
    }
    # Optimal edge length — the classic FR constant on a unit area, scaled.
    area = (2 * _CANVAS) ** 2
    k = math.sqrt(area / max(n, 1))
    temperature = _CANVAS / 4.0
    cooling = temperature / iterations

    for _ in range(iterations):
        disp: dict[str, list[float]] = {b: [0.0, 0.0] for b in bus_ids}
        # Repulsion between all bus pairs.
        for i, a in enumerate(bus_ids):
            for b in bus_ids[i + 1 :]:
                dx = pos[a][0] - pos[b][0]
                dy = pos[a][1] - pos[b][1]
                dist = math.hypot(dx, dy) or 0.01
                force = k * k / dist
                ux = dx / dist
                uy = dy / dist
                disp[a][0] += ux * force
                disp[a][1] += uy * force
                disp[b][0] -= ux * force
                disp[b][1] -= uy * force
        # Attraction along edges.
        for e in edges:
            if e.a == e.b:
                continue
            dx = pos[e.a][0] - pos[e.b][0]
            dy = pos[e.a][1] - pos[e.b][1]
            dist = math.hypot(dx, dy) or 0.01
            force = dist * dist / k
            ux = dx / dist
            uy = dy / dist
            disp[e.a][0] -= ux * force
            disp[e.a][1] -= uy * force
            disp[e.b][0] += ux * force
            disp[e.b][1] += uy * force
        # Apply with temperature cap, then clamp to the canvas.
        for b in bus_ids:
            dx, dy = disp[b]
            dmag = math.hypot(dx, dy) or 0.01
            step = min(dmag, temperature)
            pos[b][0] += dx / dmag * step
            pos[b][1] += dy / dmag * step
            pos[b][0] = max(-_CANVAS, min(_CANVAS, pos[b][0]))
            pos[b][1] = max(-_CANVAS, min(_CANVAS, pos[b][1]))
        temperature = max(temperature - cooling, 0.0)

    return {b: (xy[0], xy[1]) for b, xy in pos.items()}


def _loading_color(loading_pct: float) -> QColor:
    """Return a traffic-light colour for a branch loading percentage."""
    if not math.isfinite(loading_pct):
        return QColor("#888888")
    if loading_pct < _LOADING_GREEN_MAX:
        return QColor("#2e8b57")  # green
    if loading_pct < _LOADING_AMBER_MAX:
        return QColor("#daa520")  # amber
    if loading_pct < _LOADING_ORANGE_MAX:
        return QColor("#e07b1a")  # orange
    return QColor("#c3272b")  # red


class NetworkDiagramWidget(QGraphicsView):
    """Schematic view of the grid with results-aware line colouring."""

    def __init__(self) -> None:
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._positions: dict[str, tuple[float, float]] = {}
        self._bus_items: dict[str, QGraphicsEllipseItem] = {}
        self._edge_items: dict[tuple[str, str], QGraphicsLineItem] = {}
        self._edge_pen = QPen(QColor("#888888"), 2.5)

    # ------------------------------------------------------------------
    # Public API

    def set_study(self, study: Study) -> None:
        """Rebuild the diagram for a study and clear any result overlay."""
        self._scene.clear()
        self._bus_items.clear()
        self._edge_items.clear()
        bus_ids = [b.id for b in study.grid.buses]
        edges = _collect_edges(study.grid)
        self._positions = _spring_layout(bus_ids, edges)
        self._draw_edges(study)
        self._draw_buses(study)
        bounds = self._scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)
        self._scene.setSceneRect(bounds)
        self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def set_result(self, result: SnapshotResult) -> None:
        """Colour branches by loading percentage from a solved snapshot."""
        for br in result.branches:
            key = (br.from_bus, br.to_bus)
            edge = self._edge_items.get(key) or self._edge_items.get((br.to_bus, br.from_bus))
            if edge is None:
                continue
            pen = QPen(_loading_color(br.loading_pct), 3.0)
            edge.setPen(pen)
            tip = (
                f"{br.branch_id} ({br.kind})\n"
                f"loading: {br.loading_pct:.1f}%\n"
                f"loss: {br.loss_mw:.2f} MW"
            )
            edge.setToolTip(tip)

    # ------------------------------------------------------------------
    # Drawing helpers

    def _draw_edges(self, study: Study) -> None:
        for line in study.grid.lines:
            self._add_edge(line.from_bus.id, line.to_bus.id, label=line.id)
        for tx in study.grid.transformers:
            self._add_edge(tx.hv_bus.id, tx.lv_bus.id, label=tx.id, dashed=True)

    def _add_edge(self, a: str, b: str, *, label: str, dashed: bool = False) -> None:
        if a not in self._positions or b not in self._positions:
            return
        xa, ya = self._positions[a]
        xb, yb = self._positions[b]
        pen = QPen(self._edge_pen)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        item = QGraphicsLineItem(xa, ya, xb, yb)
        item.setPen(pen)
        item.setZValue(-1)
        item.setToolTip(label)
        self._scene.addItem(item)
        self._edge_items[(a, b)] = item

    def _draw_buses(self, study: Study) -> None:
        bus_font = QFont()
        bus_font.setPointSize(8)
        for bus in study.grid.buses:
            xy = self._positions.get(bus.id)
            if xy is None:
                continue
            x, y = xy
            rect = QRectF(x - _BUS_RADIUS, y - _BUS_RADIUS, _NODE_SIZE, _NODE_SIZE)
            color = QColor("#1f4e8c") if bus.kv >= _HV_BUS_KV else QColor("#5a8fbf")
            node = QGraphicsEllipseItem(rect)
            node.setPen(QPen(QColor("#102a44"), 1.5))
            node.setBrush(QBrush(color))
            node.setToolTip(f"{bus.id}  {bus.name}  ({bus.kv:.0f} kV, {bus.type})")
            self._scene.addItem(node)
            self._bus_items[bus.id] = node
            label = QGraphicsSimpleTextItem(bus.id)
            label.setFont(bus_font)
            label.setBrush(QBrush(QColor("#f1f1f1")))
            lw = label.boundingRect().width()
            lh = label.boundingRect().height()
            label.setPos(x - lw / 2, y - lh / 2)
            self._scene.addItem(label)
