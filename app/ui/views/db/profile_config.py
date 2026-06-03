"""ConnectionProfile <-> MySQLConfig dönüşümü ve keyring şifre erişimi.

Şifreler keyring'de saklanır:
- MySQL şifresi: account = profile.username
- SSH şifresi:   account = "__ssh__:<ssh_user>"
"""

from __future__ import annotations

from app.core.db_agent import MySQLConfig, SSHConfig
from app.models.connection_profile import ConnectionProfile
from app.services import secrets

MODULE = "database"


def ssh_account(ssh_user: str) -> str:
    return f"__ssh__:{ssh_user}"


def build_mysql_config(profile: ConnectionProfile) -> MySQLConfig:
    password = ""
    if profile.id is not None:
        password = secrets.get_password(MODULE, profile.id, profile.username) or ""

    ssh = None
    extra = profile.extra
    if extra.get("use_ssh"):
        ssh_user = extra.get("ssh_user", "")
        ssh_pw = None
        if profile.id is not None:
            ssh_pw = secrets.get_password(MODULE, profile.id, ssh_account(ssh_user))
        ssh = SSHConfig(
            host=extra.get("ssh_host", ""),
            port=int(extra.get("ssh_port", 22) or 22),
            username=ssh_user,
            password=ssh_pw,
            pkey_path=extra.get("ssh_pkey_path") or None,
        )

    return MySQLConfig(
        host=profile.host,
        port=int(profile.port or 3306),
        username=profile.username,
        password=password,
        database=extra.get("database") or None,
        ssh=ssh,
    )
