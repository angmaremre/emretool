"""Elasticsearch agent — cluster bağlantısı, index listeleme, mapping, query DSL.

Opsiyonel SSH tünel desteği (db_agent.open_tunnel) içerir. Yanıtlar düz Python
dict/list olarak döndürülür ki UI doğrudan render edebilsin.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from elasticsearch import Elasticsearch

from app.core.base_agent import BaseAgent
from app.core.db_agent import SSHConfig, open_tunnel


@dataclass
class ElasticConfig:
    host: str = "127.0.0.1"
    port: int = 9200
    scheme: str = "http"             # http | https
    username: Optional[str] = None
    password: Optional[str] = None
    verify_certs: bool = False
    request_timeout: int = 15
    ssh: Optional[SSHConfig] = None


class ElasticAgent(BaseAgent):
    def __init__(self, config: ElasticConfig) -> None:
        self._config = config
        self._client: Optional[Elasticsearch] = None
        self._tunnel = None
        self._lock = threading.RLock()

    # --- yaşam döngüsü ---

    def connect(self) -> None:
        cfg = self._config
        host, port = cfg.host, cfg.port
        if cfg.ssh is not None:
            self._tunnel = open_tunnel(cfg.ssh, host, port)
            host, port = "127.0.0.1", self._tunnel.local_bind_port

        url = f"{cfg.scheme}://{host}:{port}"
        basic_auth = (cfg.username, cfg.password or "") if cfg.username else None
        client = Elasticsearch(
            url,
            basic_auth=basic_auth,
            verify_certs=cfg.verify_certs,
            request_timeout=cfg.request_timeout,
        )
        client.info()  # bağlantıyı doğrula
        with self._lock:
            self._client = client

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:  # noqa: BLE001
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
            except Exception:  # noqa: BLE001
                return False

    def _require(self) -> Elasticsearch:
        if self._client is None:
            raise RuntimeError("Elasticsearch bağlantısı kurulmadı.")
        return self._client

    # --- introspection ---

    def list_indices(self) -> List[Dict[str, Any]]:
        with self._lock:
            client = self._require()
            resp = client.cat.indices(
                format="json", h="index,health,status,docs.count,store.size", s="index"
            )
            return list(resp.body)

    def get_mapping(self, index: str) -> Dict[str, Any]:
        with self._lock:
            client = self._require()
            return dict(client.indices.get_mapping(index=index).body)

    # --- arama (query DSL) ---

    def search(self, index: str, dsl: str, size: int = 50) -> Tuple[Dict[str, Any], int, int]:
        """DSL JSON'unu çalıştırır; (yanıt, toplam_hit, took_ms) döndürür.

        Boş DSL match_all kabul edilir. "size" DSL içinde verilmemişse parametre kullanılır.
        """
        body = json.loads(dsl) if dsl and dsl.strip() else {"query": {"match_all": {}}}
        kwargs = dict(body)
        kwargs.setdefault("size", size)
        with self._lock:
            client = self._require()
            resp = client.search(index=index, **kwargs)
        data = dict(resp.body)
        total = data.get("hits", {}).get("total", {})
        total_value = total.get("value", 0) if isinstance(total, dict) else int(total or 0)
        took = int(data.get("took", 0))
        return data, total_value, took
