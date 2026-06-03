"""Database modülü ana görünümü — bağlantı paneli + aktif connection sekmeleri."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QWidget,
)

from app.core.db_agent import MySQLAgent
from app.models.connection_profile import ConnectionProfile
from app.services.worker import run_in_background
from app.ui.base_view import BaseModuleView
from app.ui.views.db.connection_panel import ConnectionListPanel
from app.ui.views.db.connection_tab import DbConnectionTab
from app.ui.views.db.profile_config import build_mysql_config


class DatabaseView(BaseModuleView):
    def __init__(self, container, parent=None) -> None:
        super().__init__(container, parent)
        self._tab_counter = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        self._panel = ConnectionListPanel(container.storage)
        self._panel.connectRequested.connect(self._on_connect)
        self._panel.setMinimumWidth(200)
        splitter.addWidget(self._panel)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        splitter.addWidget(self._tabs)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 880])

    def _on_connect(self, profile: ConnectionProfile) -> None:
        config = build_mysql_config(profile)
        agent = MySQLAgent(config)
        self._panel.setEnabled(False)

        def connected(_result):
            self._tab_counter += 1
            key = f"database:{profile.id}:{self._tab_counter}"
            self.container.connections.register(key, agent)
            tab = DbConnectionTab(agent, profile, self.container.threadpool)
            tab.setProperty("conn_key", key)
            index = self._tabs.addTab(tab, profile.name)
            self._tabs.setCurrentIndex(index)

        def failed(exc: Exception):
            agent.close()
            QMessageBox.critical(
                self, "Bağlantı hatası", f"{profile.name} bağlanamadı:\n{exc}"
            )

        def finished():
            self._panel.setEnabled(True)

        run_in_background(
            self.container.threadpool,
            agent.connect,
            on_result=connected,
            on_error=failed,
            on_finished=finished,
        )

    def _close_tab(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if isinstance(widget, DbConnectionTab):
            key = widget.property("conn_key")
            if key:
                self.container.connections.remove(key)
            else:
                widget.close_agent()
        self._tabs.removeTab(index)
