"""Şifrelerin güvenli saklanması — işletim sistemi keyring'i (macOS Keychain vb.).

Şifreler asla SQLite'a veya log'a yazılmaz; yalnızca buradan geçer.
"""

from __future__ import annotations

from typing import Optional

import keyring

SERVICE_PREFIX = "emretool"


def _service_name(module: str, profile_id: int) -> str:
    return f"{SERVICE_PREFIX}:{module}:{profile_id}"


def _account(username: str) -> str:
    return username or "__default__"


def set_password(module: str, profile_id: int, username: str, password: str) -> None:
    if password is None:
        return
    keyring.set_password(_service_name(module, profile_id), _account(username), password)


def get_password(module: str, profile_id: int, username: str) -> Optional[str]:
    try:
        return keyring.get_password(_service_name(module, profile_id), _account(username))
    except keyring.errors.KeyringError:
        return None


def delete_password(module: str, profile_id: int, username: str) -> None:
    try:
        keyring.delete_password(_service_name(module, profile_id), _account(username))
    except keyring.errors.PasswordDeleteError:
        pass
    except keyring.errors.KeyringError:
        pass
