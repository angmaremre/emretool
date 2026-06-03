"""Kayıtlı Elasticsearch bağlantılarını gruplanabilir biçimde listeleyen panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget

from app.models.connection_profile import ConnectionProfile
from app.services import secrets
from app.services.storage import Storage
from app.ui.views.elastic.connection_dialog import ElasticConnectionDialog
from app.ui.views.elastic.profile_config import MODULE, ssh_account
from app.ui.widgets.grouped_panel import GroupedConnectionPanel


def _subtitle(profile: ConnectionProfile) -> str:
    scheme = profile.extra.get("scheme", "http")
    return f"{scheme}://{profile.host}:{profile.port}"


def _cleanup(profile: ConnectionProfile) -> None:
    if profile.username:
        secrets.delete_password(MODULE, profile.id, profile.username)
    if profile.extra.get("use_ssh"):
        secrets.delete_password(
            MODULE, profile.id, ssh_account(profile.extra.get("ssh_user", ""))
        )


class ElasticConnectionPanel(GroupedConnectionPanel):
    def __init__(self, storage: Storage, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            storage,
            module=MODULE,
            header="Elasticsearch Bağlantıları",
            dialog_factory=ElasticConnectionDialog,
            subtitle_fn=_subtitle,
            delete_cleanup=_cleanup,
            parent=parent,
        )
