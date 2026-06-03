"""Schema kopyalama — bir MySQL şemasını (kaynak SSH'li olabilir) başka bir
bağlantıya datalı veya datasız kopyalar.

Kaynak ve hedef için bağımsız ham bağlantılar açar. Veri kopyalama, büyük
tabloları bellekte tutmamak için server-side streaming cursor (SSCursor) kullanır.
Hedefte FOREIGN_KEY_CHECKS kapatılır, böylece tablo sırası önemsizdir.

Bu, read-only agent'tan AYRI bir yazma yoludur; hedef bağlantı yazılabilir açılır.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import pymysql

from app.core.db_agent import MySQLConfig, open_tunnel

ProgressFn = Callable[[str], None]


def _open_conn(cfg: MySQLConfig) -> Tuple["pymysql.connections.Connection", object]:
    """Yazılabilir ham bir bağlantı açar; (conn, tunnel) döndürür."""
    host, port = cfg.host, cfg.port
    tunnel = None
    if cfg.ssh is not None:
        tunnel = open_tunnel(cfg.ssh, host, port)
        host, port = "127.0.0.1", tunnel.local_bind_port
    conn = pymysql.connect(
        host=host,
        port=port,
        user=cfg.username,
        password=cfg.password,
        charset=cfg.charset,
        connect_timeout=cfg.connect_timeout,
        autocommit=True,
        cursorclass=pymysql.cursors.Cursor,
    )
    return conn, tunnel


class SchemaCopier:
    def __init__(
        self,
        source_cfg: MySQLConfig,
        target_cfg: MySQLConfig,
        source_schema: str,
        target_schema: str,
        include_data: bool,
        batch_size: int = 1000,
    ) -> None:
        self._source_cfg = source_cfg
        self._target_cfg = target_cfg
        self._source_schema = source_schema
        self._target_schema = target_schema
        self._include_data = include_data
        self._batch_size = batch_size

    def run(self, progress: Optional[ProgressFn] = None) -> None:
        emit = progress or (lambda _m: None)

        sconn, stun = _open_conn(self._source_cfg)
        tconn, ttun = _open_conn(self._target_cfg)
        try:
            tables = self._list_base_tables(sconn)
            emit(f"{len(tables)} tablo bulundu.")

            with tconn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self._target_schema}` "
                    f"CHARACTER SET utf8mb4"
                )
                cur.execute(f"USE `{self._target_schema}`")
                cur.execute("SET FOREIGN_KEY_CHECKS=0")

            total = len(tables)
            for i, table in enumerate(tables, 1):
                ddl = self._get_create_table(sconn, table)
                with tconn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS `{table}`")
                    cur.execute(ddl)
                emit(f"[{i}/{total}] {table} — şema oluşturuldu")

                if self._include_data:
                    copied = self._copy_data(sconn, tconn, table)
                    emit(f"[{i}/{total}] {table} — {copied} satır kopyalandı")

            with tconn.cursor() as cur:
                cur.execute("SET FOREIGN_KEY_CHECKS=1")

            mode = "veriyle" if self._include_data else "yalnızca şema"
            emit(f"Tamamlandı ✓ ({mode}, {total} tablo)")
        finally:
            self._safe_close(sconn, stun)
            self._safe_close(tconn, ttun)

    # --- iç yardımcılar ---

    def _list_base_tables(self, sconn) -> List[str]:
        with sconn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                 WHERE table_schema = %s AND table_type = 'BASE TABLE'
                 ORDER BY table_name
                """,
                (self._source_schema,),
            )
            return [r[0] for r in cur.fetchall()]

    def _get_create_table(self, sconn, table: str) -> str:
        with sconn.cursor() as cur:
            cur.execute(f"SHOW CREATE TABLE `{self._source_schema}`.`{table}`")
            return cur.fetchone()[1]

    def _copy_data(self, sconn, tconn, table: str) -> int:
        with sconn.cursor(pymysql.cursors.SSCursor) as scur:
            scur.execute(f"SELECT * FROM `{self._source_schema}`.`{table}`")
            columns = [d[0] for d in scur.description]
            collist = ", ".join(f"`{c}`" for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            insert_sql = (
                f"INSERT INTO `{self._target_schema}`.`{table}` "
                f"({collist}) VALUES ({placeholders})"
            )
            total = 0
            while True:
                batch = scur.fetchmany(self._batch_size)
                if not batch:
                    break
                with tconn.cursor() as tcur:
                    tcur.executemany(insert_sql, batch)
                total += len(batch)
            return total

    @staticmethod
    def _safe_close(conn, tunnel) -> None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        if tunnel is not None:
            try:
                tunnel.stop()
            except Exception:  # noqa: BLE001
                pass
