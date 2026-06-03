"""Sol navigation sidebar — modüller arası geçiş ve tema değiştirici."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_NAME, SIDEBAR_WIDTH

if TYPE_CHECKING:
    from app.core.module_registry import ModuleDescriptor


class Sidebar(QWidget):
    moduleSelected = pyqtSignal(str)   # modül key'i
    themeToggled = pyqtSignal()

    def __init__(self, modules: "List[ModuleDescriptor]", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(2)

        title = QLabel(APP_NAME)
        title.setObjectName("SidebarTitle")
        layout.addWidget(title)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for index, module in enumerate(modules):
            btn = QPushButton(f"  {module.icon}   {module.title}")
            btn.setObjectName("SidebarButton")
            btn.setCheckable(True)
            btn.setProperty("module_key", module.key)
            if index == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked, k=module.key: self.moduleSelected.emit(k))
            self._group.addButton(btn)
            layout.addWidget(btn)

        layout.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        theme_btn = QPushButton("◐  Tema değiştir")
        theme_btn.setObjectName("Ghost")
        theme_btn.clicked.connect(self.themeToggled.emit)
        layout.addWidget(theme_btn)
