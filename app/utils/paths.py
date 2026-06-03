"""Platforma uygun uygulama veri dizinleri."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.config import APP_NAME


def app_data_dir() -> Path:
    """Kullanıcıya özel uygulama veri dizinini döndürür (yoksa oluşturur)."""
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", str(home)))
    else:  # linux / diğer
        base = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share")))

    target = base / APP_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def database_path() -> Path:
    """Lokal SQLite veritabanının yolu (connection profilleri vb.)."""
    return app_data_dir() / "emretool.db"
