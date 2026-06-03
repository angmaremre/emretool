"""Henüz geliştirilmemiş modüller için geçici içerik widget'ı."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderContent(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        big = QLabel(title)
        big.setStyleSheet("font-size: 22px; font-weight: 600;")
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)

        small = QLabel(subtitle)
        small.setObjectName("PanelLabel")
        small.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(big)
        layout.addWidget(small)
