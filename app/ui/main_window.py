"""Ana pencere — sidebar + modül view'lerini barındıran stacked alan."""

from __future__ import annotations

from typing import Dict

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from app.config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
)
from app.core.container import ServiceContainer
from app.core.module_registry import ModuleRegistry
from app.ui.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self, container: ServiceContainer, registry: ModuleRegistry) -> None:
        super().__init__()
        self._container = container
        self._registry = registry
        self._index_by_key: Dict[str, int] = {}

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(900, 600)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        modules = registry.modules()
        self._sidebar = Sidebar(modules)
        self._sidebar.moduleSelected.connect(self._on_module_selected)
        self._sidebar.themeToggled.connect(self._on_theme_toggled)
        root.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        for module in modules:
            view = module.view_factory(container)
            self._index_by_key[module.key] = self._stack.addWidget(view)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Hazır")

    def _on_module_selected(self, key: str) -> None:
        if key in self._index_by_key:
            self._stack.setCurrentIndex(self._index_by_key[key])

    def _on_theme_toggled(self) -> None:
        tm = self._container.theme_manager
        if tm is not None:
            theme = tm.toggle()
            self.statusBar().showMessage(f"Tema: {theme}", 2000)

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt imzası
        self._container.shutdown()
        super().closeEvent(event)
