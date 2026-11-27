"""Workbench main window: open a study, solve a scenario, view results."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pypowerlines.errors import InputError, NumericalError
from pypowerlines.io import load_study
from pypowerlines.solver import solve_scenario

from .diagram import NetworkDiagramWidget
from .models import (
    branch_model,
    bus_model,
    conductor_model,
    populate_from_result,
    transformer_model,
)

if TYPE_CHECKING:
    from pypowerlines.model import Study


class MainWindow(QMainWindow):
    """Top-level window that hosts the whole workbench."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PyPowerlines")
        self.resize(1200, 720)

        self._study: Study | None = None

        self._scenario_combo = QComboBox()
        self._scenario_combo.setMinimumWidth(240)
        self._run_button = QPushButton("Run scenario")
        self._run_button.setEnabled(False)
        self._run_button.clicked.connect(self._on_run_clicked)

        self._loss_label = QLabel("No scenario solved yet")
        self._loss_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._buses = bus_model()
        self._branches = branch_model()
        self._conductors = conductor_model()
        self._transformers = transformer_model()

        self._diagram = NetworkDiagramWidget()

        self._tabs = QTabWidget()
        self._tabs.addTab(self._diagram, "Diagram")
        self._tabs.addTab(_table_view(self._buses), "Buses")
        self._tabs.addTab(_table_view(self._branches), "Branches")
        self._tabs.addTab(_table_view(self._conductors), "Conductors")
        self._tabs.addTab(_table_view(self._transformers), "Transformers")

        top = QHBoxLayout()
        top.addWidget(QLabel("Scenario:"))
        top.addWidget(self._scenario_combo, stretch=1)
        top.addWidget(self._run_button)
        top.addSpacing(16)
        top.addWidget(self._loss_label, stretch=1)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(self._tabs, stretch=1)
        self.setCentralWidget(central)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Open a study to begin.")
        self._build_menu()

    # ------------------------------------------------------------------
    # Wiring

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()
        if menu_bar is None:  # pragma: no cover - PyQt always returns a bar
            return
        file_menu = menu_bar.addMenu("&File")
        if file_menu is None:  # pragma: no cover
            return
        open_action = QAction("&Open study…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_clicked)
        file_menu.addAction(open_action)

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

    # ------------------------------------------------------------------
    # Slots

    def _on_open_clicked(self) -> None:
        start = str(Path.cwd())
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open study",
            start,
            "Study YAML (*.yaml *.yml);;All files (*)",
        )
        if not path_str:
            return
        self._load_study(Path(path_str))

    def _on_run_clicked(self) -> None:
        if self._study is None:
            return
        scenario_id = self._scenario_combo.currentData()
        if not isinstance(scenario_id, str):
            return
        scenario = next((s for s in self._study.scenarios if s.id == scenario_id), None)
        if scenario is None:
            return
        self._status.showMessage(f"Solving {scenario_id}…")
        self._run_button.setEnabled(False)
        try:
            result = solve_scenario(self._study, scenario)
        except NumericalError as exc:
            self._run_button.setEnabled(True)
            self._status.showMessage("Solver failed.")
            QMessageBox.critical(self, "Solver error", str(exc))
            return
        self._run_button.setEnabled(True)
        populate_from_result(
            buses=self._buses,
            branches=self._branches,
            conductors=self._conductors,
            transformers=self._transformers,
            result=result,
        )
        self._diagram.set_result(result)
        self._loss_label.setText(
            f"Coupled total loss: {result.total_loss_mw:.2f} MW"
            f"   |   Fixed-R baseline: {result.total_loss_fixed_r_mw:.2f} MW"
            f"   |   NR iters: {result.nr_iterations}, "
            f"coupling passes: {result.coupling_passes}",
        )
        warn_suffix = f"  ({len(result.warnings)} warnings)" if result.warnings else ""
        self._status.showMessage(f"Solved {scenario_id}.{warn_suffix}")

    # ------------------------------------------------------------------
    # Helpers

    def _load_study(self, path: Path) -> None:
        try:
            study = load_study(path)
        except InputError as exc:
            QMessageBox.critical(self, "Study load failed", str(exc))
            return
        self._study = study
        self.setWindowTitle(f"PyPowerlines — {study.id}")
        self._diagram.set_study(study)
        self._scenario_combo.clear()
        for s in study.scenarios:
            self._scenario_combo.addItem(f"{s.id} — {s.name}", s.id)
        self._run_button.setEnabled(bool(study.scenarios))
        self._loss_label.setText("Pick a scenario and press Run.")
        self._buses.set_rows([])
        self._branches.set_rows([])
        self._conductors.set_rows([])
        self._transformers.set_rows([])
        self._status.showMessage(
            f"Loaded {study.id}: {len(study.grid.buses)} buses, "
            f"{len(study.grid.lines)} lines, {len(study.scenarios)} scenarios.",
        )


def _table_view(model: object) -> QTableView:
    view = QTableView()
    view.setModel(model)  # type: ignore[arg-type]
    view.setSortingEnabled(False)
    view.setAlternatingRowColors(True)
    horiz = view.horizontalHeader()
    if horiz is not None:
        horiz.setStretchLastSection(True)
    vert = view.verticalHeader()
    if vert is not None:
        vert.setVisible(False)
    return view
