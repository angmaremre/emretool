"""Modül view'leri için ortak taban sınıf."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtWidgets import QWidget

if TYPE_CHECKING:
    from app.core.container import ServiceContainer


class BaseModuleView(QWidget):
    def __init__(self, container: "ServiceContainer", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.container = container
