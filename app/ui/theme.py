"""Tema yönetimi — dark (varsayılan) ve light, VS Code / Postman tarzı.

Tema seçimi SQLite ayarlarında saklanır ve uygulama açılışında geri yüklenir.
"""

from __future__ import annotations

from typing import Dict

from PyQt6.QtWidgets import QApplication

from app.services.storage import Storage

SETTING_KEY = "ui.theme"

DARK: Dict[str, str] = {
    "bg": "#1e1e1e",
    "panel": "#252526",
    "panel_alt": "#2d2d30",
    "border": "#3c3c3c",
    "text": "#d4d4d4",
    "text_dim": "#9d9d9d",
    "accent": "#0e639c",
    "accent_hover": "#1177bb",
    "selection": "#094771",
    "input_bg": "#3c3c3c",
    "input_text": "#e8e8e8",
}

LIGHT: Dict[str, str] = {
    "bg": "#f3f3f3",
    "panel": "#ffffff",
    "panel_alt": "#ececec",
    "border": "#d0d0d0",
    "text": "#1f1f1f",
    "text_dim": "#6b6b6b",
    "accent": "#0e639c",
    "accent_hover": "#1177bb",
    "selection": "#cce5ff",
    "input_bg": "#ffffff",
    "input_text": "#1f1f1f",
}

PALETTES = {"dark": DARK, "light": LIGHT}


def _build_qss(p: Dict[str, str]) -> str:
    return f"""
    QWidget {{
        background-color: {p['bg']};
        color: {p['text']};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background-color: {p['bg']}; }}

    /* Sidebar */
    #Sidebar {{
        background-color: {p['panel']};
        border-right: 1px solid {p['border']};
    }}
    #SidebarTitle {{
        font-size: 16px;
        font-weight: 600;
        padding: 16px 14px 10px 14px;
        color: {p['text']};
    }}
    #SidebarButton {{
        text-align: left;
        padding: 9px 14px;
        border: none;
        border-radius: 0px;
        background-color: transparent;
        color: {p['text_dim']};
    }}
    #SidebarButton:hover {{ background-color: {p['panel_alt']}; color: {p['text']}; }}
    #SidebarButton:checked {{
        background-color: {p['accent']};
        color: #ffffff;
        border-left: 3px solid {p['accent_hover']};
        padding-left: 11px;
        font-weight: 600;
    }}
    #SidebarButton:checked:hover {{ background-color: {p['accent_hover']}; color: #ffffff; }}

    /* Panel başlıkları */
    #ViewHeader {{
        font-size: 18px;
        font-weight: 600;
        padding: 14px 16px;
    }}
    #PanelLabel {{ color: {p['text_dim']}; font-weight: 600; }}

    /* Girişler */
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
        background-color: {p['input_bg']};
        color: {p['input_text']};
        border: 1px solid {p['border']};
        border-radius: 4px;
        padding: 5px 7px;
        selection-background-color: {p['accent']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {p['accent']};
    }}

    /* Butonlar */
    QPushButton {{
        background-color: {p['accent']};
        color: #ffffff;
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background-color: {p['accent_hover']}; }}
    QPushButton:disabled {{ background-color: {p['panel_alt']}; color: {p['text_dim']}; }}
    QPushButton#Ghost {{
        background-color: transparent;
        color: {p['text']};
        border: 1px solid {p['border']};
    }}
    QPushButton#Ghost:hover {{ background-color: {p['panel_alt']}; }}

    /* Tablolar */
    QTableView, QTreeView, QListWidget {{
        background-color: {p['panel']};
        alternate-background-color: {p['panel_alt']};
        border: 1px solid {p['border']};
        gridline-color: {p['border']};
        selection-background-color: {p['accent']};
        selection-color: #ffffff;
    }}
    QListWidget::item:selected, QTreeView::item:selected, QTableView::item:selected {{
        background-color: {p['accent']};
        color: #ffffff;
    }}
    QHeaderView::section {{
        background-color: {p['panel_alt']};
        color: {p['text']};
        padding: 5px 8px;
        border: none;
        border-right: 1px solid {p['border']};
        border-bottom: 1px solid {p['border']};
        font-weight: 600;
    }}

    /* Sekmeler */
    QTabWidget::pane {{ border: 1px solid {p['border']}; }}
    QTabBar::tab {{
        background-color: {p['panel']};
        color: {p['text_dim']};
        padding: 7px 14px;
        border: 1px solid {p['border']};
        border-bottom: none;
    }}
    QTabBar::tab:selected {{ background-color: {p['bg']}; color: {p['text']}; }}

    /* Çeşitli */
    QSplitter::handle {{ background-color: {p['border']}; }}
    QStatusBar {{ background-color: {p['panel']}; color: {p['text_dim']}; }}
    QScrollBar:vertical {{ background: {p['bg']}; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 6px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {p['text_dim']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


class ThemeManager:
    def __init__(self, app: QApplication, storage: Storage) -> None:
        self._app = app
        self._storage = storage
        self._current = storage.get_setting(SETTING_KEY, "light") or "light"

    def current_theme(self) -> str:
        return self._current

    def apply(self, theme: str) -> None:
        palette = PALETTES.get(theme, DARK)
        self._current = theme if theme in PALETTES else "dark"
        self._app.setStyleSheet(_build_qss(palette))
        self._storage.set_setting(SETTING_KEY, self._current)

    def toggle(self) -> str:
        self.apply("light" if self._current == "dark" else "dark")
        return self._current
