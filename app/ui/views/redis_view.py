"""Redis modülü ana görünümü — bağlantı paneli + aktif bağlantı sekmeleri."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QMessageBox, QSplitter, QTabWidget

from app.core.redis_agent import RedisAgent
from app.models.connection_profile import ConnectionProfile
from app.services.worker import run_in_background
from app.ui.base_view import BaseModuleView
from app.ui.views.redis.connection_panel import RedisConnectionPanel
from app.ui.views.redis.connection_tab import RedisConnectionTab
from app.ui.views.redis.profile_config import build_redis_config


class RedisView(BaseModuleView):
    def __init__(self, container, parent=None) -> None:
        super().__init__(container, parent)
        self._tab_counter = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        self._panel = RedisConnectionPanel(container.storage)
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
        agent = RedisAgent(build_redis_config(profile))
        self._panel.setEnabled(False)

        def connected(_):
            self._tab_counter += 1
            key = f"redis:{profile.id}:{self._tab_counter}"
            self.container.connections.register(key, agent)
            tab = RedisConnectionTab(agent, self.container.threadpool)
            tab.setProperty("conn_key", key)
            index = self._tabs.addTab(tab, profile.name)
            self._tabs.setCurrentIndex(index)

        def failed(exc: Exception):
            agent.close()
            QMessageBox.critical(self, "Bağlantı hatası", f"{profile.name} bağlanamadı:\n{exc}")

        def finished():
            self._panel.setEnabled(True)

        run_in_background(
            self.container.threadpool, agent.connect,
            on_result=connected, on_error=failed, on_finished=finished,
        )

    def _close_tab(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if isinstance(widget, RedisConnectionTab):
            key = widget.property("conn_key")
            if key:
                self.container.connections.remove(key)
            else:
                widget.close_agent()
        self._tabs.removeTab(index)
