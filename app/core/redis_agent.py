"""Redis agent — bağlantı, key tarama/arama, tip/TTL, value görüntüleme ve güvenli edit.

Key listeleme SCAN ile yapılır (bloklayan KEYS kullanılmaz). Opsiyonel SSH tünel
desteği vardır (db_agent.open_tunnel yeniden kullanılır).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import redis

from app.core.base_agent import BaseAgent
from app.core.db_agent import SSHConfig, open_tunnel


@dataclass
class RedisConfig:
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    socket_timeout: int = 10
    ssh: Optional[SSHConfig] = None


@dataclass
class KeyInfo:
    key: str
    type: str
    ttl: int            # -1 = expire yok, -2 = key yok


class RedisAgent(BaseAgent):
    EDITABLE_TYPES = {"string", "hash"}

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._client: Optional[redis.Redis] = None
        self._tunnel = None
        self._lock = threading.RLock()

    # --- yaşam döngüsü ---

    def connect(self) -> None:
        cfg = self._config
        host, port = cfg.host, cfg.port
        if cfg.ssh is not None:
            self._tunnel = open_tunnel(cfg.ssh, host, port)
            host, port = "127.0.0.1", self._tunnel.local_bind_port

        client = redis.Redis(
            host=host,
            port=port,
            db=cfg.db,
            password=cfg.password or None,
            socket_timeout=cfg.socket_timeout,
            socket_connect_timeout=cfg.socket_timeout,
            decode_responses=True,
        )
        client.ping()
        with self._lock:
            self._client = client

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except redis.RedisError:
                    pass
                self._client = None
            if self._tunnel is not None:
                try:
                    self._tunnel.stop()
                except Exception:  # noqa: BLE001
                    pass
                self._tunnel = None

    @property
    def is_connected(self) -> bool:
        with self._lock:
            if self._client is None:
                return False
            try:
                return bool(self._client.ping())
            except redis.RedisError:
                return False

    def _require(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis bağlantısı kurulmadı.")
        return self._client

    # --- tarama / arama ---

    def scan_keys(self, pattern: str = "*", max_keys: int = 1000) -> Tuple[List[str], bool]:
        """Pattern'e uyan key'leri SCAN ile döndürür; (keys, kesildi_mi)."""
        with self._lock:
            client = self._require()
            keys: List[str] = []
            for key in client.scan_iter(match=pattern or "*", count=500):
                keys.append(key)
                if len(keys) >= max_keys:
                    return sorted(keys), True
            return sorted(keys), False

    def key_info(self, key: str) -> KeyInfo:
        with self._lock:
            client = self._require()
            return KeyInfo(key=key, type=client.type(key), ttl=client.ttl(key))

    def get_value(self, key: str, max_items: int = 1000) -> Any:
        """Key tipine göre değeri döndürür."""
        with self._lock:
            client = self._require()
            ktype = client.type(key)
            if ktype == "string":
                return client.get(key)
            if ktype == "hash":
                return client.hgetall(key)
            if ktype == "list":
                return client.lrange(key, 0, max_items - 1)
            if ktype == "set":
                members = list(client.smembers(key))
                return members[:max_items]
            if ktype == "zset":
                return client.zrange(key, 0, max_items - 1, withscores=True)
            if ktype == "none":
                return None
            return f"(görüntüleme desteklenmiyor: {ktype})"

    # --- güvenli edit ---

    def set_string(self, key: str, value: str, keep_ttl: bool = True) -> None:
        with self._lock:
            self._require().set(key, value, keepttl=keep_ttl)

    def set_hash_field(self, key: str, field: str, value: str) -> None:
        with self._lock:
            self._require().hset(key, field, value)

    def set_ttl(self, key: str, seconds: int) -> None:
        """seconds <= 0 ise expire kaldırılır (persist)."""
        with self._lock:
            client = self._require()
            if seconds and seconds > 0:
                client.expire(key, seconds)
            else:
                client.persist(key)

    def delete(self, key: str) -> None:
        with self._lock:
            self._require().delete(key)
