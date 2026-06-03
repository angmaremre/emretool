"""SQLite tabanlı kalıcı depolama: bağlantı profilleri ve uygulama ayarları.

Şifreler burada saklanmaz (bkz. services.secrets). Her işlem için kısa ömürlü
bir bağlantı açılır; böylece arka plan thread'lerinden güvenle çağrılabilir.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from app.models.connection_profile import ConnectionProfile
from app.utils.paths import database_path


class Storage:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = str(db_path) if db_path else str(database_path())
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS connection_profiles (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    module    TEXT NOT NULL,
                    name      TEXT NOT NULL,
                    host      TEXT NOT NULL DEFAULT 'localhost',
                    port      INTEGER NOT NULL DEFAULT 0,
                    username  TEXT NOT NULL DEFAULT '',
                    extra     TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

    # --- bağlantı profilleri ---

    def list_profiles(self, module: Optional[str] = None) -> list[ConnectionProfile]:
        with self._conn() as conn:
            if module:
                rows = conn.execute(
                    "SELECT * FROM connection_profiles WHERE module = ? ORDER BY name",
                    (module,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM connection_profiles ORDER BY module, name"
                ).fetchall()
        return [ConnectionProfile.from_row(dict(r)) for r in rows]

    def get_profile(self, profile_id: int) -> Optional[ConnectionProfile]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM connection_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        return ConnectionProfile.from_row(dict(row)) if row else None

    def save_profile(self, profile: ConnectionProfile) -> int:
        """Profili ekler veya günceller; profil id'sini döndürür."""
        with self._conn() as conn:
            if profile.id is None:
                cur = conn.execute(
                    """
                    INSERT INTO connection_profiles (module, name, host, port, username, extra)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile.module,
                        profile.name,
                        profile.host,
                        profile.port,
                        profile.username,
                        profile.extra_json(),
                    ),
                )
                profile.id = int(cur.lastrowid)
            else:
                conn.execute(
                    """
                    UPDATE connection_profiles
                       SET name = ?, host = ?, port = ?, username = ?, extra = ?,
                           updated_at = datetime('now')
                     WHERE id = ?
                    """,
                    (
                        profile.name,
                        profile.host,
                        profile.port,
                        profile.username,
                        profile.extra_json(),
                        profile.id,
                    ),
                )
        return profile.id

    def delete_profile(self, profile_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM connection_profiles WHERE id = ?", (profile_id,))

    # --- ayarlar (key/value) ---

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
