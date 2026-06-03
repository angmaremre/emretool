"""Yeniden kullanılabilir form alanları."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget


class PasswordField(QWidget):
    """Şifre girişi + "Göster/Gizle" düğmesi.

    ``QLineEdit`` ile aynı temel arayüzü (``text``/``setText``/
    ``setPlaceholderText``) sunar; mevcut dialog kodu değişmeden çalışır.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.edit, 1)

        self._toggle = QPushButton("Göster")
        self._toggle.setObjectName("Ghost")
        self._toggle.setCheckable(True)
        self._toggle.setFixedWidth(80)
        self._toggle.setToolTip("Şifreyi göster/gizle")
        self._toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self._toggle)

    def _on_toggle(self, shown: bool) -> None:
        self.edit.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
        self._toggle.setText("Gizle" if shown else "Göster")

    # --- QLineEdit uyumlu yardımcılar ---

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:  # noqa: N802 (Qt stili)
        self.edit.setText(value)

    def setPlaceholderText(self, value: str) -> None:  # noqa: N802
        self.edit.setPlaceholderText(value)
