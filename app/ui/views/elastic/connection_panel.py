"""Kayıtlı Elasticsearch bağlantılarını listeleyen sol panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.connection_profile import ConnectionProfile
from app.services import secrets
from app.services.storage import Storage
from app.ui.views.elastic.connection_dialog import ElasticConnectionDialog
from app.ui.views.elastic.profile_config import MODULE, ssh_account

_PROFILE_ROLE = Qt.ItemDataRole.UserRole


class ElasticConnectionPanel(QWidget):
    connectRequested = pyqtSignal(object)

    def __init__(self, storage: Storage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._storage = storage

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        header = QLabel("Elasticsearch Bağlantıları")
        header.setObjectName("PanelLabel")
        layout.addWidget(header)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self._connect())
        layout.addWidget(self._list, 1)

        row = QHBoxLayout()
        new_btn = QPushButton("+ Yeni")
        new_btn.clicked.connect(self._new)
        connect_btn = QPushButton("Bağlan")
        connect_btn.clicked.connect(self._connect)
        row.addWidget(new_btn)
        row.addWidget(connect_btn)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        edit_btn = QPushButton("Düzenle")
        edit_btn.setObjectName("Ghost")
        edit_btn.clicked.connect(self._edit)
        del_btn = QPushButton("Sil")
        del_btn.setObjectName("Ghost")
        del_btn.clicked.connect(self._delete)
        row2.addWidget(edit_btn)
        row2.addWidget(del_btn)
        layout.addLayout(row2)

        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        for profile in self._storage.list_profiles(MODULE):
            scheme = profile.extra.get("scheme", "http")
            item = QListWidgetItem(f"{profile.name}\n{scheme}://{profile.host}:{profile.port}")
            item.setData(_PROFILE_ROLE, profile)
            self._list.addItem(item)

    def _selected(self) -> Optional[ConnectionProfile]:
        item = self._list.currentItem()
        return item.data(_PROFILE_ROLE) if item else None

    def _new(self) -> None:
        if ElasticConnectionDialog(self._storage, parent=self).exec():
            self.refresh()

    def _edit(self) -> None:
        profile = self._selected()
        if profile is None:
            return
        if ElasticConnectionDialog(self._storage, profile=profile, parent=self).exec():
            self.refresh()

    def _delete(self) -> None:
        profile = self._selected()
        if profile is None or profile.id is None:
            return
        if QMessageBox.question(
            self, "Bağlantıyı sil", f"'{profile.name}' silinsin mi?"
        ) == QMessageBox.StandardButton.Yes:
            if profile.username:
                secrets.delete_password(MODULE, profile.id, profile.username)
            if profile.extra.get("use_ssh"):
                secrets.delete_password(
                    MODULE, profile.id, ssh_account(profile.extra.get("ssh_user", ""))
                )
            self._storage.delete_profile(profile.id)
            self.refresh()

    def _connect(self) -> None:
        profile = self._selected()
        if profile is not None:
            self.connectRequested.emit(profile)
