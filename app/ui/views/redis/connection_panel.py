"""Kayıtlı Redis bağlantılarını gruplanabilir biçimde listeleyen panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget

from app.models.connection_profile import ConnectionProfile
from app.services import secrets
from app.services.storage import Storage
from app.ui.views.redis.connection_dialog import RedisConnectionDialog
from app.ui.views.redis.profile_config import MODULE, ssh_account
from app.ui.widgets.grouped_panel import GroupedConnectionPanel


def _subtitle(profile: ConnectionProfile) -> str:
    return f"{profile.host}:{profile.port}/{profile.extra.get('db', 0)}"


def _cleanup(profile: ConnectionProfile) -> None:
    secrets.delete_password(MODULE, profile.id, profile.username)
    if profile.extra.get("use_ssh"):
        secrets.delete_password(
            MODULE, profile.id, ssh_account(profile.extra.get("ssh_user", ""))
        )


class RedisConnectionPanel(GroupedConnectionPanel):
    def __init__(self, storage: Storage, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            storage,
            module=MODULE,
            header="Redis Bağlantıları",
            dialog_factory=RedisConnectionDialog,
            subtitle_fn=_subtitle,
            delete_cleanup=_cleanup,
            parent=parent,
        )
