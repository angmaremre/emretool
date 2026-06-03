"""ConnectionProfile <-> RedisConfig dönüşümü ve keyring şifre erişimi."""

from __future__ import annotations

from app.core.db_agent import SSHConfig
from app.core.redis_agent import RedisConfig
from app.models.connection_profile import ConnectionProfile
from app.services import secrets

MODULE = "redis"


def ssh_account(ssh_user: str) -> str:
    return f"__ssh__:{ssh_user}"


def build_redis_config(profile: ConnectionProfile) -> RedisConfig:
    password = None
    if profile.id is not None:
        password = secrets.get_password(MODULE, profile.id, profile.username)

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

    return RedisConfig(
        host=profile.host,
        port=int(profile.port or 6379),
        db=int(extra.get("db", 0) or 0),
        password=password or None,
        ssh=ssh,
    )
