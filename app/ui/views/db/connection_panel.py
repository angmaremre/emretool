"""Kayıtlı MySQL bağlantı profillerini gruplanabilir biçimde listeleyen panel."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtWidgets import QWidget

from app.models.connection_profile import ConnectionProfile
from app.services import secrets
from app.services.storage import Storage
from app.ui.views.db.connection_dialog import ConnectionDialog
from app.ui.views.db.profile_config import MODULE, ssh_account
from app.ui.views.db.schema_copy_dialog import SchemaCopyDialog
from app.ui.widgets.grouped_panel import GroupedConnectionPanel


def _subtitle(profile: ConnectionProfile) -> str:
    return f"{profile.host}:{profile.port}"


def _cleanup(profile: ConnectionProfile) -> None:
    secrets.delete_password(MODULE, profile.id, profile.username)
    if profile.extra.get("use_ssh"):
        secrets.delete_password(
            MODULE, profile.id, ssh_account(profile.extra.get("ssh_user", ""))
        )


class ConnectionListPanel(GroupedConnectionPanel):
    def __init__(self, storage: Storage, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            storage,
            module=MODULE,
            header="Bağlantılar",
            dialog_factory=ConnectionDialog,
            subtitle_fn=_subtitle,
            delete_cleanup=_cleanup,
            parent=parent,
        )

    def extra_buttons(self) -> List[tuple]:
        return [("⇄  Schema Kopyala", self._open_schema_copy)]

    def _open_schema_copy(self) -> None:
        SchemaCopyDialog(self._storage, parent=self).exec()
