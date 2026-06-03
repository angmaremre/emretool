"""Tema yönetimi — dark (varsayılan) ve light, VS Code / Postman tarzı.

Tema seçimi SQLite ayarlarında saklanır ve uygulama açılışında geri yüklenir.
"""

from __future__ import annotations

from typing import Dict, Tuple

from PyQt6.QtWidgets import QApplication

from app.services.storage import Storage
from app.utils.paths import app_data_dir

SETTING_KEY = "ui.theme"


def _close_icon_svg(color: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
        'viewBox="0 0 12 12">'
        f'<line x1="3" y1="3" x2="9" y2="9" stroke="{color}" '
        'stroke-width="1.6" stroke-linecap="round"/>'
        f'<line x1="9" y1="3" x2="3" y2="9" stroke="{color}" '
        'stroke-width="1.6" stroke-linecap="round"/></svg>'
    )


def _write_close_icons(p: Dict[str, str]) -> Tuple[str, str]:
    """Tema rengine uygun sekme-kapat (×) ikonlarını yazar; (normal, hover) yol döndürür.

    Qt QSS varsayılan kapat butonunu açık temada beyaz/görünmez çizebiliyor;
    kendi SVG'mizi üretip rengini palete göre veriyoruz.
    """
    try:
        icons_dir = app_data_dir() / "icons"
        icons_dir.mkdir(parents=True, exist_ok=True)
        normal = icons_dir / "tabclose.svg"
        hover = icons_dir / "tabclose_hover.svg"
        normal.write_text(_close_icon_svg(p["text_dim"]), encoding="utf-8")
        hover.write_text(_close_icon_svg(p["accent_hover"]), encoding="utf-8")
        # QSS forward-slash bekler; macOS yolunda boşluk olabilir → tırnakla.
        return normal.as_posix(), hover.as_posix()
    except OSError:
        return "", ""

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


def _build_qss(p: Dict[str, str], close_icon: str = "", close_hover: str = "") -> str:
    if close_icon:
        close_qss = f"""
    QTabBar::close-button {{
        image: url("{close_icon}");
        subcontrol-position: right;
        padding: 2px;
        margin-left: 6px;
    }}
    QTabBar::close-button:hover {{ image: url("{close_hover}"); }}
    """
    else:
        close_qss = ""
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
    /* Bağlantı listesi: öğeleri birbirinden ayır (okunabilirlik) */
    QListWidget::item {{ padding: 6px 5px; }}
    #ConnTree::item {{
        padding: 6px 5px;
        border-bottom: 1px solid {p['border']};
    }}
    #ConnTree {{ outline: 0; }}
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
    {close_qss}

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
        close_icon, close_hover = _write_close_icons(palette)
        self._app.setStyleSheet(_build_qss(palette, close_icon, close_hover))
        self._storage.set_setting(SETTING_KEY, self._current)

    def toggle(self) -> str:
        self.apply("light" if self._current == "dark" else "dark")
        return self._current
