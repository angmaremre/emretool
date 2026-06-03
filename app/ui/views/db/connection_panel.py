"""Kayıtlı bağlantı profillerini listeleyen sol panel."""

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
from app.ui.views.db.connection_dialog import ConnectionDialog
from app.ui.views.db.profile_config import MODULE, ssh_account
from app.ui.views.db.schema_copy_dialog import SchemaCopyDialog

_PROFILE_ROLE = Qt.ItemDataRole.UserRole


class ConnectionListPanel(QWidget):
    connectRequested = pyqtSignal(object)   # ConnectionProfile

    def __init__(self, storage: Storage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._storage = storage

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        header = QLabel("Bağlantılar")
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

        copy_btn = QPushButton("⇄  Schema Kopyala")
        copy_btn.setObjectName("Ghost")
        copy_btn.clicked.connect(self._open_schema_copy)
        layout.addWidget(copy_btn)

        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        for profile in self._storage.list_profiles(MODULE):
            item = QListWidgetItem(f"{profile.name}\n{profile.host}:{profile.port}")
            item.setData(_PROFILE_ROLE, profile)
            self._list.addItem(item)

    def _selected_profile(self) -> Optional[ConnectionProfile]:
        item = self._list.currentItem()
        return item.data(_PROFILE_ROLE) if item else None

    def _new(self) -> None:
        dialog = ConnectionDialog(self._storage, parent=self)
        if dialog.exec():
            self.refresh()

    def _edit(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        dialog = ConnectionDialog(self._storage, profile=profile, parent=self)
        if dialog.exec():
            self.refresh()

    def _delete(self) -> None:
        profile = self._selected_profile()
        if profile is None or profile.id is None:
            return
        confirm = QMessageBox.question(
            self,
            "Bağlantıyı sil",
            f"'{profile.name}' bağlantısı silinsin mi?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            secrets.delete_password(MODULE, profile.id, profile.username)
            if profile.extra.get("use_ssh"):
                secrets.delete_password(
                    MODULE, profile.id, ssh_account(profile.extra.get("ssh_user", ""))
                )
            self._storage.delete_profile(profile.id)
            self.refresh()

    def _connect(self) -> None:
        profile = self._selected_profile()
        if profile is not None:
            self.connectRequested.emit(profile)

    def _open_schema_copy(self) -> None:
        SchemaCopyDialog(self._storage, parent=self).exec()
