"""Açık (aktif) bağlantıların hafif yöneticisi.

Her modülün agent örnekleri burada bir anahtarla tutulur; uygulama kapanırken
hepsi düzgünce kapatılır. Agent'ların ``close()`` metodu olması beklenir.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ConnectionManager:
    def __init__(self) -> None:
        self._active: Dict[str, Any] = {}

    def register(self, key: str, agent: Any) -> None:
        # Aynı anahtarda eski bir bağlantı varsa önce kapat.
        if key in self._active:
            self.remove(key)
        self._active[key] = agent

    def get(self, key: str) -> Optional[Any]:
        return self._active.get(key)

    def keys(self) -> list[str]:
        return list(self._active.keys())

    def remove(self, key: str) -> None:
        agent = self._active.pop(key, None)
        if agent is not None:
            _safe_close(agent)

    def close_all(self) -> None:
        for agent in self._active.values():
            _safe_close(agent)
        self._active.clear()


def _safe_close(agent: Any) -> None:
    close = getattr(agent, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001 — kapatma hataları sessizce yutulur
            pass
