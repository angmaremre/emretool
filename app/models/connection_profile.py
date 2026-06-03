"""Modüllerden bağımsız bağlantı profili modeli.

Şifreler bu modelde TUTULMAZ; keyring üzerinden (services.secrets) saklanır.
Modüle özgü alanlar (db adı, SSH ayarları, TLS vb.) ``extra`` içinde tutulur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConnectionProfile:
    module: str                       # "database" | "redis" | "elastic"
    name: str                         # kullanıcının verdiği görünen ad
    host: str = "localhost"
    port: int = 0
    username: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    id: Optional[int] = None

    # --- serileştirme yardımcıları ---

    def extra_json(self) -> str:
        return json.dumps(self.extra, ensure_ascii=False)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ConnectionProfile":
        raw_extra = row.get("extra") or "{}"
        try:
            extra = json.loads(raw_extra)
        except (ValueError, TypeError):
            extra = {}
        return cls(
            id=row.get("id"),
            module=row["module"],
            name=row["name"],
            host=row.get("host", "localhost"),
            port=row.get("port", 0),
            username=row.get("username", ""),
            extra=extra,
        )
