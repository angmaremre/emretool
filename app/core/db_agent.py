"""Database agent — MySQL bağlantısı, schema introspection ve read-only sorgu.

Opsiyonel SSH tünel desteği (sshtunnel) içerir. Bu katman tamamen UI'dan
bağımsızdır; yalnızca veri erişimiyle ilgilenir.

Güvenlik: yalnızca read-only ifadeler (SELECT/SHOW/DESCRIBE/EXPLAIN/WITH) çalıştırılır;
ayrıca oturum sunucu tarafında READ ONLY olarak işaretlenir. Çoklu statement (";" ile
ayrılmış) reddedilir.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

import pymysql

from app.core.base_agent import BaseAgent

# read-only kabul edilen ilk anahtar kelimeler
_READ_ONLY_PREFIXES = ("select", "show", "describe", "desc", "explain", "with")

# satır içi/blok yorumları kaldırmak için
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")


@dataclass
class SSHConfig:
    host: str
    port: int = 22
    username: str = ""
    password: Optional[str] = None
    pkey_path: Optional[str] = None


@dataclass
class MySQLConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    username: str = "root"
    password: str = ""
    database: Optional[str] = None
    charset: str = "utf8mb4"
    connect_timeout: int = 10
    ssh: Optional[SSHConfig] = None


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    key: str
    default: Any
    extra: str


@dataclass
class QueryResult:
    columns: List[str] = field(default_factory=list)
    rows: List[tuple] = field(default_factory=list)
    rowcount: int = 0
    truncated: bool = False
    execution_ms: float = 0.0


def normalize_sql(sql: str) -> str:
    """Yorumları ve baştaki/sondaki boşlukları temizler."""
    cleaned = _COMMENT_RE.sub(" ", sql)
    cleaned = _LINE_COMMENT_RE.sub(" ", cleaned)
    return cleaned.strip().rstrip(";").strip()


def is_read_only(sql: str) -> bool:
    """SQL'in salt-okunur tek bir ifade olup olmadığını kontrol eder."""
    cleaned = normalize_sql(sql)
    if not cleaned:
        return False
    # çoklu statement engeli (ortada ";" varsa reddet)
    if ";" in cleaned:
        return False
    first = cleaned.split(None, 1)[0].lower()
    return first in _READ_ONLY_PREFIXES


class ReadOnlyViolation(Exception):
    """Read-only olmayan bir sorgu çalıştırılmaya çalışıldığında fırlatılır."""


class MySQLAgent(BaseAgent):
    def __init__(self, config: MySQLConfig) -> None:
        self._config = config
        self._conn: Optional[pymysql.connections.Connection] = None
        self._tunnel = None  # SSHTunnelForwarder

    # --- bağlantı yaşam döngüsü ---

    def connect(self) -> None:
        cfg = self._config
        host, port = cfg.host, cfg.port

        if cfg.ssh is not None:
            host, port = self._open_tunnel(cfg, host, port)

        self._conn = pymysql.connect(
            host=host,
            port=port,
            user=cfg.username,
            password=cfg.password,
            database=cfg.database or None,
            charset=cfg.charset,
            connect_timeout=cfg.connect_timeout,
            autocommit=True,
            cursorclass=pymysql.cursors.Cursor,
        )
        # Oturumu sunucu tarafında salt-okunur işaretle (ek güvenlik katmanı).
        try:
            with self._conn.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
        except pymysql.MySQLError:
            # Bazı MySQL türevleri desteklemeyebilir; istemci tarafı doğrulama yine geçerli.
            pass

    def _open_tunnel(self, cfg: MySQLConfig, host: str, port: int) -> tuple[str, int]:
        from sshtunnel import SSHTunnelForwarder

        ssh = cfg.ssh
        self._tunnel = SSHTunnelForwarder(
            (ssh.host, ssh.port),
            ssh_username=ssh.username,
            ssh_password=ssh.password or None,
            ssh_pkey=ssh.pkey_path or None,
            remote_bind_address=(host, port),
        )
        self._tunnel.start()
        return "127.0.0.1", self._tunnel.local_bind_port

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except pymysql.MySQLError:
                pass
            self._conn = None
        if self._tunnel is not None:
            try:
                self._tunnel.stop()
            except Exception:  # noqa: BLE001
                pass
            self._tunnel = None

    @property
    def is_connected(self) -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.ping(reconnect=False)
            return True
        except pymysql.MySQLError:
            return False

    # --- schema introspection ---

    def list_databases(self) -> List[str]:
        rows = self._fetch_all(
            "SELECT schema_name FROM information_schema.schemata ORDER BY schema_name"
        )
        return [r[0] for r in rows]

    def list_tables(self, database: str) -> List[str]:
        rows = self._fetch_all(
            """
            SELECT table_name FROM information_schema.tables
             WHERE table_schema = %s
             ORDER BY table_name
            """,
            (database,),
        )
        return [r[0] for r in rows]

    def get_columns(self, database: str, table: str) -> List[ColumnInfo]:
        rows = self._fetch_all(
            """
            SELECT column_name, column_type, is_nullable, column_key,
                   column_default, extra
              FROM information_schema.columns
             WHERE table_schema = %s AND table_name = %s
             ORDER BY ordinal_position
            """,
            (database, table),
        )
        return [
            ColumnInfo(
                name=r[0],
                type=r[1],
                nullable=(str(r[2]).upper() == "YES"),
                key=r[3] or "",
                default=r[4],
                extra=r[5] or "",
            )
            for r in rows
        ]

    def get_create_table(self, database: str, table: str) -> str:
        rows = self._fetch_all(f"SHOW CREATE TABLE `{database}`.`{table}`")
        return rows[0][1] if rows else ""

    # --- read-only sorgu ---

    def run_query(self, sql: str, max_rows: int = 1000) -> QueryResult:
        if not is_read_only(sql):
            raise ReadOnlyViolation(
                "Yalnızca read-only sorgulara izin verilir "
                "(SELECT, SHOW, DESCRIBE, EXPLAIN, WITH)."
            )
        conn = self._require_conn()
        start = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(normalize_sql(sql))
            columns = [d[0] for d in cur.description] if cur.description else []
            fetched = cur.fetchmany(max_rows + 1)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        truncated = len(fetched) > max_rows
        rows = list(fetched[:max_rows])
        return QueryResult(
            columns=columns,
            rows=rows,
            rowcount=len(rows),
            truncated=truncated,
            execution_ms=elapsed_ms,
        )

    # --- iç yardımcılar ---

    def _require_conn(self) -> "pymysql.connections.Connection":
        if self._conn is None:
            raise RuntimeError("Bağlantı kurulmadı. Önce connect() çağrılmalı.")
        return self._conn

    def _fetch_all(self, sql: str, params: tuple = ()) -> List[tuple]:
        conn = self._require_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
