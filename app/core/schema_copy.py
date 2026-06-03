"""Schema kopyalama — bir MySQL şemasını (kaynak SSH'li olabilir) başka bir
bağlantıya datalı veya datasız kopyalar.

En hızlı yöntem: ``mysqldump | mysql`` pipe'ı. Tek streaming akış, çok-satırlı
(extended) INSERT'ler ve otomatik key/FK devre dışı bırakma sayesinde satır-satır
kopyalamadan kat kat hızlıdır. mysqldump/mysql binary'leri bulunamazsa saf-Python
yöntemine (SSCursor + executemany) düşer.

Şifreler argv'ye yazılmaz; geçici, 0600 izinli bir ``--defaults-extra-file`` ile
geçirilir ve iş bitince silinir. SSH gerekiyorsa lokal tünel açılır.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Callable, List, Optional, Tuple

import pymysql

from app.core.db_agent import MySQLConfig, open_tunnel

ProgressFn = Callable[[str], None]

_BINARY_DIRS = [
    "/usr/local/mysql/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
]


def _find_binary(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    for directory in _BINARY_DIRS:
        candidate = os.path.join(directory, name)
        if os.path.exists(candidate):
            return candidate
    return None


def _open_conn(cfg: MySQLConfig) -> Tuple["pymysql.connections.Connection", object]:
    """Yazılabilir ham bir bağlantı açar; (conn, tunnel) döndürür."""
    host, port, tunnel = _resolve(cfg)
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


def _resolve(cfg: MySQLConfig) -> Tuple[str, int, object]:
    """SSH varsa tünel açıp lokal (host, port, tunnel); yoksa doğrudan döndürür."""
    if cfg.ssh is not None:
        tunnel = open_tunnel(cfg.ssh, cfg.host, cfg.port)
        return "127.0.0.1", tunnel.local_bind_port, tunnel
    return cfg.host, cfg.port, None


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
        dump_bin = _find_binary("mysqldump")
        mysql_bin = _find_binary("mysql")
        if dump_bin and mysql_bin:
            self._run_mysqldump(emit, dump_bin, mysql_bin)
        else:
            emit("mysqldump/mysql bulunamadı — Python yöntemine geçiliyor (daha yavaş).")
            self._run_python(emit)

    # --- ortak yardımcılar ---

    def _source_charset_collation(self) -> Tuple[str, Optional[str]]:
        """Kaynak şemanın varsayılan charset/collation'ını okur (yoksa utf8mb4)."""
        conn, tun = _open_conn(self._source_cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT default_character_set_name, default_collation_name "
                    "FROM information_schema.schemata WHERE schema_name = %s",
                    (self._source_schema,),
                )
                row = cur.fetchone()
            if row and row[0]:
                return row[0], row[1]
            return "utf8mb4", None
        finally:
            self._safe_close(conn, tun)

    def _create_db_sql(self, charset: str, collation: Optional[str]) -> str:
        """Hedef şemayı kaynakla aynı charset/collation ile oluşturan SQL.

        charset/collation değerleri sunucunun information_schema'sından gelir
        (güvenilir), bu yüzden doğrudan kullanılır.
        """
        sql = (
            f"CREATE DATABASE IF NOT EXISTS `{self._target_schema}` "
            f"CHARACTER SET {charset}"
        )
        if collation:
            sql += f" COLLATE {collation}"
        return sql

    # --- en hızlı yöntem: mysqldump | mysql ---

    def _run_mysqldump(self, emit: ProgressFn, dump_bin: str, mysql_bin: str) -> None:
        s_tun = t_tun = None
        s_cnf = t_cnf = None
        try:
            s_host, s_port, s_tun = _resolve(self._source_cfg)
            t_host, t_port, t_tun = _resolve(self._target_cfg)
            s_cnf = self._write_defaults(self._source_cfg, s_host, s_port)
            t_cnf = self._write_defaults(self._target_cfg, t_host, t_port)

            emit("Hedef şema hazırlanıyor…")
            charset, collation = self._source_charset_collation()
            self._mysql_exec(mysql_bin, t_cnf, self._create_db_sql(charset, collation))
            emit(
                f"Hedef şema '{self._target_schema}' hazır "
                f"(charset={charset}{', ' + collation if collation else ''})."
            )

            dump_cmd = [
                dump_bin,
                f"--defaults-extra-file={s_cnf}",
                "--single-transaction",
                "--quick",
                "--routines",
                "--triggers",
                "--events",
                "--set-gtid-purged=OFF",
                "--verbose",
            ]
            if not self._include_data:
                dump_cmd.append("--no-data")
            dump_cmd.append(self._source_schema)

            import_cmd = [
                mysql_bin,
                f"--defaults-extra-file={t_cnf}",
                self._target_schema,
            ]

            emit("Kopyalama başladı (mysqldump | mysql)…")
            dumper = subprocess.Popen(
                dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            importer = subprocess.Popen(
                import_cmd, stdin=dumper.stdout,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            dumper.stdout.close()  # importer'a SIGPIPE iletilebilsin

            # mysqldump --verbose ilerlemeyi stderr'e yazar; tablo satırlarını yansıt.
            for raw in dumper.stderr:
                text = raw.decode(errors="replace").strip().lstrip("- ").strip()
                if "table structure for table" in text or "Dumping data for table" in text:
                    emit(text)

            dumper.wait()
            imp_out, imp_err = importer.communicate()

            if dumper.returncode not in (0, None):
                raise RuntimeError(f"mysqldump hata kodu {dumper.returncode}")
            if importer.returncode not in (0, None):
                msg = imp_err.decode(errors="replace").strip() or "bilinmeyen hata"
                raise RuntimeError(f"mysql import hatası: {msg}")

            mode = "veriyle" if self._include_data else "yalnızca şema"
            emit(f"Tamamlandı ✓ ({mode}, mysqldump)")
        finally:
            for cnf in (s_cnf, t_cnf):
                if cnf and os.path.exists(cnf):
                    os.remove(cnf)
            for tun in (s_tun, t_tun):
                if tun is not None:
                    try:
                        tun.stop()
                    except Exception:  # noqa: BLE001
                        pass

    def _write_defaults(self, cfg: MySQLConfig, host: str, port: int) -> str:
        fd, path = tempfile.mkstemp(prefix="emretool_my_", suffix=".cnf")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("[client]\n")
            f.write(f"host={host}\n")
            f.write(f"port={port}\n")
            f.write(f"user={cfg.username}\n")
            if cfg.password:
                f.write(f'password="{cfg.password}"\n')
        return path

    def _mysql_exec(self, mysql_bin: str, cnf: str, sql: str) -> None:
        result = subprocess.run(
            [mysql_bin, f"--defaults-extra-file={cnf}", "-e", sql],
            capture_output=True,
        )
        if result.returncode != 0:
            msg = result.stderr.decode(errors="replace").strip() or "bilinmeyen hata"
            raise RuntimeError(msg)

    # --- yedek yöntem: saf Python (binary yoksa) ---

    def _run_python(self, emit: ProgressFn) -> None:
        sconn, stun = _open_conn(self._source_cfg)
        tconn, ttun = _open_conn(self._target_cfg)
        try:
            tables = self._list_base_tables(sconn)
            emit(f"{len(tables)} tablo bulundu.")

            charset, collation = self._source_charset_collation()
            with tconn.cursor() as cur:
                cur.execute(self._create_db_sql(charset, collation))
                cur.execute(f"USE `{self._target_schema}`")
                cur.execute("SET FOREIGN_KEY_CHECKS=0")
                cur.execute("SET UNIQUE_CHECKS=0")

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
                cur.execute("SET UNIQUE_CHECKS=1")

            mode = "veriyle" if self._include_data else "yalnızca şema"
            emit(f"Tamamlandı ✓ ({mode}, {total} tablo)")
        finally:
            self._safe_close(sconn, stun)
            self._safe_close(tconn, ttun)

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
