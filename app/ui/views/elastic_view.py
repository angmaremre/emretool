"""Elasticsearch modülü görünümü (yer tutucu)."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout

from app.ui.base_view import BaseModuleView
from app.ui.widgets.placeholder import PlaceholderContent


class ElasticView(BaseModuleView):
    def __init__(self, container, parent=None) -> None:
        super().__init__(container, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            PlaceholderContent(
                "🔍  Elasticsearch",
                "Cluster bağlantısı, index/mapping görüntüleme ve query DSL — yakında.",
            )
        )
