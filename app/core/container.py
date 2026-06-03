"""Basit servis konteyneri (dependency injection).

View ve agent'lara servisler bu konteyner üzerinden geçilir; böylece UI katmanı
somut servis kurulumuna değil, tek bir bağımlılık noktasına bağlı kalır.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThreadPool

from app.services.connection_manager import ConnectionManager
from app.services.storage import Storage


class ServiceContainer:
    def __init__(self, storage: Optional[Storage] = None) -> None:
        self.storage: Storage = storage or Storage()
        self.connections = ConnectionManager()
        self.threadpool = QThreadPool.globalInstance()
        # QApplication kurulduktan sonra atanır:
        self.theme_manager = None

    def shutdown(self) -> None:
        self.connections.close_all()
