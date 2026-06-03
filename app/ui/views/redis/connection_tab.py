"""Tek bir aktif Redis bağlantısının çalışma alanı.

Sol: pattern arama + key listesi (SCAN ile).
Sağ: seçilen key'in tipi/TTL'i, value görüntüleme ve güvenli edit (string/hash),
TTL ayarlama ve key silme.
"""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QListWidget,
)

from app.core.redis_agent import RedisAgent
from app.services.worker import run_in_background


class RedisConnectionTab(QWidget):
    def __init__(self, agent: RedisAgent, threadpool, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._agent = agent
        self._pool = threadpool
        self._current_key: Optional[str] = None
        self._current_type: Optional[str] = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        # --- sol: arama + key listesi ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        search_row = QHBoxLayout()
        self._pattern = QLineEdit("*")
        self._pattern.setPlaceholderText("pattern (örn: user:*)")
        self._pattern.returnPressed.connect(self._search)
        search_btn = QPushButton("Ara")
        search_btn.clicked.connect(self._search)
        search_row.addWidget(self._pattern, 1)
        search_row.addWidget(search_btn)
        left_layout.addLayout(search_row)
        self._key_count = QLabel("")
        self._key_count.setObjectName("PanelLabel")
        left_layout.addWidget(self._key_count)
        self._keys = QListWidget()
        self._keys.itemSelectionChanged.connect(self._on_key_selected)
        left_layout.addWidget(self._keys, 1)
        splitter.addWidget(left)

        # --- sağ: value görüntüleme/edit ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        info_row = QHBoxLayout()
        self._info = QLabel("Bir key seç")
        self._info.setObjectName("PanelLabel")
        info_row.addWidget(self._info, 1)
        info_row.addWidget(QLabel("TTL(sn):"))
        self._ttl = QSpinBox()
        self._ttl.setRange(-1, 2_000_000_000)
        ttl_btn = QPushButton("TTL ayarla")
        ttl_btn.setObjectName("Ghost")
        ttl_btn.clicked.connect(self._apply_ttl)
        info_row.addWidget(self._ttl)
        info_row.addWidget(ttl_btn)
        del_btn = QPushButton("Sil")
        del_btn.setObjectName("Ghost")
        del_btn.clicked.connect(self._delete_key)
        info_row.addWidget(del_btn)
        right_layout.addLayout(info_row)

        # value alanı: string (editör) | hash (tablo) | diğer (read-only)
        self._stack = QStackedWidget()
        self._string_edit = QPlainTextEdit()
        self._hash_table = QTableWidget(0, 2)
        self._hash_table.setHorizontalHeaderLabels(["Alan", "Değer"])
        self._hash_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._hash_table.itemChanged.connect(self._on_hash_item_changed)
        self._readonly = QPlainTextEdit()
        self._readonly.setReadOnly(True)
        self._stack.addWidget(self._string_edit)   # 0
        self._stack.addWidget(self._hash_table)     # 1
        self._stack.addWidget(self._readonly)       # 2
        right_layout.addWidget(self._stack, 1)

        self._save_btn = QPushButton("Kaydet")
        self._save_btn.clicked.connect(self._save_string)
        self._save_btn.setEnabled(False)
        right_layout.addWidget(self._save_btn)

        splitter.addWidget(right)
        splitter.setSizes([300, 680])

        self._search()

    # --- arama ---

    def _search(self) -> None:
        pattern = self._pattern.text().strip() or "*"
        self._key_count.setText("aranıyor…")

        def done(result):
            keys, truncated = result
            self._keys.clear()
            self._keys.addItems(keys)
            self._key_count.setText(
                f"{len(keys)} key" + (" (ilk 1000, kesildi)" if truncated else "")
            )

        run_in_background(
            self._pool, self._agent.scan_keys,
            args=(pattern, 1000), on_result=done, on_error=self._error,
        )

    # --- key seçimi ---

    def _on_key_selected(self) -> None:
        item = self._keys.currentItem()
        if item is None:
            return
        key = item.text()
        self._current_key = key

        def done(payload):
            info, value = payload
            self._current_type = info.type
            self._info.setText(f"{key}  ·  tip: {info.type}  ·  TTL: {info.ttl}")
            self._ttl.setValue(info.ttl if info.ttl and info.ttl > 0 else -1)
            self._render_value(info.type, value)

        def load():
            info = self._agent.key_info(key)
            value = self._agent.get_value(key)
            return info, value

        run_in_background(self._pool, load, on_result=done, on_error=self._error)

    def _render_value(self, ktype: str, value: Any) -> None:
        if ktype == "string":
            self._string_edit.blockSignals(True)
            self._string_edit.setPlainText("" if value is None else str(value))
            self._string_edit.blockSignals(False)
            self._stack.setCurrentIndex(0)
            self._save_btn.setEnabled(True)
        elif ktype == "hash":
            self._hash_table.blockSignals(True)
            self._hash_table.setRowCount(0)
            for field, val in (value or {}).items():
                r = self._hash_table.rowCount()
                self._hash_table.insertRow(r)
                field_item = QTableWidgetItem(str(field))
                field_item.setFlags(field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._hash_table.setItem(r, 0, field_item)
                self._hash_table.setItem(r, 1, QTableWidgetItem(str(val)))
            self._hash_table.blockSignals(False)
            self._stack.setCurrentIndex(1)
            self._save_btn.setEnabled(False)
        else:
            text = self._format_other(value)
            self._readonly.setPlainText(text)
            self._stack.setCurrentIndex(2)
            self._save_btn.setEnabled(False)

    @staticmethod
    def _format_other(value: Any) -> str:
        if isinstance(value, list):
            lines = []
            for item in value:
                if isinstance(item, tuple) and len(item) == 2:  # zset (member, score)
                    lines.append(f"{item[0]}  =  {item[1]}")
                else:
                    lines.append(str(item))
            return "\n".join(lines)
        return "" if value is None else str(value)

    # --- edit / güvenli yazma ---

    def _save_string(self) -> None:
        if not self._current_key or self._current_type != "string":
            return
        value = self._string_edit.toPlainText()

        def done(_):
            self._info.setText(f"{self._current_key}  ·  kaydedildi ✓")

        run_in_background(
            self._pool, self._agent.set_string,
            args=(self._current_key, value), on_result=done, on_error=self._error,
        )

    def _on_hash_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 1 or not self._current_key:
            return
        field_item = self._hash_table.item(item.row(), 0)
        if field_item is None:
            return
        field = field_item.text()
        value = item.text()
        run_in_background(
            self._pool, self._agent.set_hash_field,
            args=(self._current_key, field, value),
            on_error=self._error,
        )

    def _apply_ttl(self) -> None:
        if not self._current_key:
            return
        run_in_background(
            self._pool, self._agent.set_ttl,
            args=(self._current_key, self._ttl.value()),
            on_error=self._error,
        )

    def _delete_key(self) -> None:
        if not self._current_key:
            return
        if QMessageBox.question(
            self, "Key sil", f"'{self._current_key}' silinsin mi?"
        ) != QMessageBox.StandardButton.Yes:
            return
        key = self._current_key

        def done(_):
            self._current_key = None
            self._search()

        run_in_background(
            self._pool, self._agent.delete, args=(key,),
            on_result=done, on_error=self._error,
        )

    def _error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Redis hatası", str(exc))

    def close_agent(self) -> None:
        self._agent.close()
