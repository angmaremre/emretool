"""Gruplanabilir bağlantı paneli — tüm modüller (DB/Redis/Elastic) ortak kullanır.

Bağlantılar bir ağaçta gösterilir; kullanıcı gruplar oluşturup profilleri
sürükle-bırak ile gruplar arasında taşıyabilir. Grup bilgisi profilin
``extra["group"]`` alanında, grup listesi ise ayarlarda (``<module>.groups``)
saklanır (boş gruplar da korunur). Hiç özel grup yoksa düz liste gösterilir
(geriye dönük uyumlu).
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.connection_profile import ConnectionProfile
from app.services.storage import Storage

PROFILE_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1      # "group" | "profile"
GROUP_ROLE = Qt.ItemDataRole.UserRole + 2      # grup adı (str; "" = gruplanmamış)

_UNGROUPED_LABEL = "Gruplanmamış"


class _ConnectionTree(QTreeWidget):
    """Sürükle-bırakta grup atamasını panele devreden ağaç."""

    def __init__(self, drop_handler: Callable, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._drop_handler = drop_handler

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt stili)
        self._drop_handler(event)


class GroupedConnectionPanel(QWidget):
    connectRequested = pyqtSignal(object)   # ConnectionProfile

    def __init__(
        self,
        storage: Storage,
        module: str,
        header: str,
        dialog_factory: Callable[..., object],
        subtitle_fn: Callable[[ConnectionProfile], str],
        delete_cleanup: Callable[[ConnectionProfile], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._storage = storage
        self._module = module
        self._dialog_factory = dialog_factory
        self._subtitle_fn = subtitle_fn
        self._delete_cleanup = delete_cleanup

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        header_lbl = QLabel(header)
        header_lbl.setObjectName("PanelLabel")
        layout.addWidget(header_lbl)

        self._tree = _ConnectionTree(self._handle_drop)
        self._tree.setObjectName("ConnTree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._tree, 1)

        row = QHBoxLayout()
        new_btn = QPushButton("+ Yeni")
        new_btn.clicked.connect(self._new)
        connect_btn = QPushButton("Bağlan")
        connect_btn.clicked.connect(self._connect)
        row.addWidget(new_btn)
        row.addWidget(connect_btn)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        edit_btn = QPushButton("Düzenle")
        edit_btn.setObjectName("Ghost")
        edit_btn.clicked.connect(self._edit)
        del_btn = QPushButton("Sil")
        del_btn.setObjectName("Ghost")
        del_btn.clicked.connect(self._delete)
        row2.addWidget(edit_btn)
        row2.addWidget(del_btn)
        layout.addLayout(row2)

        group_btn = QPushButton("+ Grup")
        group_btn.setObjectName("Ghost")
        group_btn.setToolTip("Yeni grup oluştur (profilleri sürükleyip bırak)")
        group_btn.clicked.connect(self._new_group)
        layout.addWidget(group_btn)

        for text, callback in self.extra_buttons():
            btn = QPushButton(text)
            btn.setObjectName("Ghost")
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        self.refresh()

    # --- alt sınıflar için kanca ---

    def extra_buttons(self) -> List[tuple]:
        """(metin, callback) listesi — DB modülü Schema Kopyala düğmesi ekler."""
        return []

    # --- grup kalıcılığı ---

    def _settings_key(self) -> str:
        return f"{self._module}.groups"

    def _load_groups(self) -> List[str]:
        raw = self._storage.get_setting(self._settings_key(), "")
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return [str(g) for g in data if str(g).strip()]
        except (ValueError, TypeError):
            return []

    def _save_groups(self, groups: List[str]) -> None:
        self._storage.set_setting(self._settings_key(), json.dumps(groups, ensure_ascii=False))

    # --- ağacı doldur ---

    def refresh(self) -> None:
        self._tree.clear()
        profiles = self._storage.list_profiles(self._module)

        persisted = self._load_groups()
        groups: List[str] = []
        for g in persisted:
            if g not in groups:
                groups.append(g)
        for p in profiles:
            g = (p.extra.get("group") or "").strip()
            if g and g not in groups:
                groups.append(g)
        if set(groups) != set(persisted):
            self._save_groups(groups)

        if not groups:
            # Hiç grup yok: düz liste (geriye dönük uyumlu).
            for p in profiles:
                self._tree.addTopLevelItem(self._make_profile_node(p))
            return

        ungrouped = self._make_group_node("", _UNGROUPED_LABEL)
        self._tree.addTopLevelItem(ungrouped)
        nodes = {"": ungrouped}
        for g in groups:
            node = self._make_group_node(g, g)
            self._tree.addTopLevelItem(node)
            nodes[g] = node

        for p in profiles:
            g = (p.extra.get("group") or "").strip()
            parent = nodes.get(g, ungrouped)
            parent.addChild(self._make_profile_node(p))

        self._tree.expandAll()

    def _make_group_node(self, value: str, label: str) -> QTreeWidgetItem:
        node = QTreeWidgetItem([label])
        node.setData(0, KIND_ROLE, "group")
        node.setData(0, GROUP_ROLE, value)
        node.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        font = node.font(0)
        font.setWeight(QFont.Weight.Bold)
        node.setFont(0, font)
        return node

    def _make_profile_node(self, profile: ConnectionProfile) -> QTreeWidgetItem:
        node = QTreeWidgetItem([f"{profile.name}\n{self._subtitle_fn(profile)}"])
        node.setData(0, PROFILE_ROLE, profile)
        node.setData(0, KIND_ROLE, "profile")
        node.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        return node

    # --- sürükle-bırak ---

    def _group_at(self, item: Optional[QTreeWidgetItem]) -> str:
        if item is None:
            return ""
        if item.data(0, KIND_ROLE) == "group":
            return item.data(0, GROUP_ROLE) or ""
        parent = item.parent()
        if parent is not None and parent.data(0, KIND_ROLE) == "group":
            return parent.data(0, GROUP_ROLE) or ""
        return ""

    def _handle_drop(self, event) -> None:
        target = self._tree.itemAt(event.position().toPoint())
        group = self._group_at(target)
        changed = False
        for item in self._tree.selectedItems():
            if item.data(0, KIND_ROLE) != "profile":
                continue
            profile = item.data(0, PROFILE_ROLE)
            if profile is None or profile.id is None:
                continue
            if (profile.extra.get("group") or "").strip() != group:
                profile.extra["group"] = group
                self._storage.save_profile(profile)
                changed = True
        event.acceptProposedAction()
        if changed:
            self.refresh()

    # --- seçim / eylemler ---

    def _selected_profile(self) -> Optional[ConnectionProfile]:
        item = self._tree.currentItem()
        if item is not None and item.data(0, KIND_ROLE) == "profile":
            return item.data(0, PROFILE_ROLE)
        return None

    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.data(0, KIND_ROLE) == "profile":
            self._connect()

    def _connect(self) -> None:
        profile = self._selected_profile()
        if profile is not None:
            self.connectRequested.emit(profile)

    def _new(self) -> None:
        if self._dialog_factory(self._storage, parent=self).exec():
            self.refresh()

    def _edit(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        if self._dialog_factory(self._storage, profile=profile, parent=self).exec():
            self.refresh()

    def _delete(self) -> None:
        profile = self._selected_profile()
        if profile is None or profile.id is None:
            return
        if QMessageBox.question(
            self, "Bağlantıyı sil", f"'{profile.name}' silinsin mi?"
        ) == QMessageBox.StandardButton.Yes:
            self._delete_cleanup(profile)
            self._storage.delete_profile(profile.id)
            self.refresh()

    # --- grup yönetimi ---

    def _new_group(self) -> None:
        name, ok = QInputDialog.getText(self, "Yeni grup", "Grup adı:")
        name = name.strip()
        if not ok or not name:
            return
        groups = self._load_groups()
        if name not in groups:
            groups.append(name)
            self._save_groups(groups)
            self.refresh()

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None or item.data(0, KIND_ROLE) != "group":
            return
        group = item.data(0, GROUP_ROLE) or ""
        if not group:  # "Gruplanmamış" yeniden adlandırılamaz/silinemez
            return
        menu = QMenu(self)
        rename = menu.addAction("Grubu yeniden adlandır")
        delete = menu.addAction("Grubu sil")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen == rename:
            self._rename_group(group)
        elif chosen == delete:
            self._delete_group(group)

    def _rename_group(self, old: str) -> None:
        new, ok = QInputDialog.getText(
            self, "Grubu yeniden adlandır", "Yeni ad:", text=old
        )
        new = new.strip()
        if not ok or not new or new == old:
            return
        for p in self._storage.list_profiles(self._module):
            if (p.extra.get("group") or "").strip() == old:
                p.extra["group"] = new
                self._storage.save_profile(p)
        groups = [new if g == old else g for g in self._load_groups()]
        # olası tekrarları temizle
        deduped: List[str] = []
        for g in groups:
            if g not in deduped:
                deduped.append(g)
        self._save_groups(deduped)
        self.refresh()

    def _delete_group(self, group: str) -> None:
        if QMessageBox.question(
            self, "Grubu sil",
            f"'{group}' grubu silinsin mi? İçindeki bağlantılar "
            "'Gruplanmamış' altına taşınır.",
        ) != QMessageBox.StandardButton.Yes:
            return
        for p in self._storage.list_profiles(self._module):
            if (p.extra.get("group") or "").strip() == group:
                p.extra["group"] = ""
                self._storage.save_profile(p)
        self._save_groups([g for g in self._load_groups() if g != group])
        self.refresh()
