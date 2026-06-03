"""Uygulama giriş noktası.

Çalıştırmak için (proje kökünden):
    .venv/bin/python -m app.main
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from app.config import APP_NAME, APP_VERSION, ORG_NAME
from app.core.container import ServiceContainer
from app.core.module_registry import ModuleRegistry
from app.modules import register_builtin_modules
from app.ui.main_window import MainWindow
from app.ui.theme import ThemeManager


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)

    container = ServiceContainer()

    theme = ThemeManager(app, container.storage)
    container.theme_manager = theme
    theme.apply(theme.current_theme())

    registry = ModuleRegistry()
    register_builtin_modules(registry)

    window = MainWindow(container, registry)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
