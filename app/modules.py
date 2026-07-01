"""Yerleşik modüllerin registry'ye kaydı.

Yeni bir modül eklemek için: view sınıfını yazıp burada bir ModuleDescriptor ile
kaydetmek yeterli. Sidebar ve ana pencere otomatik olarak modülü gösterir.
"""

from __future__ import annotations

from app.core.module_registry import ModuleDescriptor, ModuleRegistry
from app.ui.views.db_view import DatabaseView
from app.ui.views.elastic_view import ElasticView
from app.ui.views.isbank_view import IsbankView
from app.ui.views.redis_view import RedisView


def register_builtin_modules(registry: ModuleRegistry) -> None:
    registry.register(
        ModuleDescriptor(
            key="database",
            title="Database",
            icon="🗄",
            order=10,
            view_factory=lambda c: DatabaseView(c),
        )
    )
    registry.register(
        ModuleDescriptor(
            key="redis",
            title="Redis",
            icon="⚡",
            order=20,
            view_factory=lambda c: RedisView(c),
        )
    )
    registry.register(
        ModuleDescriptor(
            key="elastic",
            title="Elasticsearch",
            icon="🔍",
            order=30,
            view_factory=lambda c: ElasticView(c),
        )
    )
    registry.register(
        ModuleDescriptor(
            key="isbank",
            title="İşbank Sertifika Yönetimi",
            icon="🔐",
            order=40,
            view_factory=lambda c: IsbankView(c),
        )
    )
