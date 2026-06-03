"""Tek bir aktif Elasticsearch bağlantısının çalışma alanı.

Sol: index listesi (health / doc sayısı).
Sağ: seçili index için mapping görüntüleme ve query DSL çalıştırma; sonuçlar
okunabilir (pretty) JSON olarak gösterilir.
"""

from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.elastic_agent import ElasticAgent
from app.services.worker import run_in_background

_DEFAULT_DSL = '{\n  "query": {\n    "match_all": {}\n  }\n}'
_INDEX_ROLE = Qt.ItemDataRole.UserRole


class ElasticConnectionTab(QWidget):
    def __init__(self, agent: ElasticAgent, threadpool, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._agent = agent
        self._pool = threadpool
        self._current_index: Optional[str] = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        # --- sol: index listesi ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        head_row = QHBoxLayout()
        title = QLabel("Index'ler")
        title.setObjectName("PanelLabel")
        head_row.addWidget(title, 1)
        refresh_btn = QPushButton("Yenile")
        refresh_btn.setObjectName("Ghost")
        refresh_btn.clicked.connect(self._load_indices)
        head_row.addWidget(refresh_btn)
        left_layout.addLayout(head_row)
        self._indices = QListWidget()
        self._indices.itemSelectionChanged.connect(self._on_index_selected)
        left_layout.addWidget(self._indices, 1)
        splitter.addWidget(left)

        # --- sağ: query + sonuç ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self._index_label = QLabel("index seç")
        self._index_label.setObjectName("PanelLabel")
        toolbar.addWidget(self._index_label, 1)
        mapping_btn = QPushButton("Mapping")
        mapping_btn.setObjectName("Ghost")
        mapping_btn.clicked.connect(self._show_mapping)
        toolbar.addWidget(mapping_btn)
        toolbar.addWidget(QLabel("size:"))
        self._size = QSpinBox()
        self._size.setRange(1, 10000)
        self._size.setValue(50)
        toolbar.addWidget(self._size)
        self._run_btn = QPushButton("▶ Çalıştır")
        self._run_btn.clicked.connect(self._run)
        toolbar.addWidget(self._run_btn)
        right_layout.addLayout(toolbar)

        splitter_v = QSplitter(Qt.Orientation.Vertical)
        self._editor = QPlainTextEdit()
        self._editor.setPlainText(_DEFAULT_DSL)
        splitter_v.addWidget(self._editor)
        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._result.setPlaceholderText("Sonuçlar burada görünecek…")
        splitter_v.addWidget(self._result)
        splitter_v.setSizes([170, 380])
        right_layout.addWidget(splitter_v, 1)

        self._status = QLabel("")
        self._status.setObjectName("PanelLabel")
        right_layout.addWidget(self._status)

        splitter.addWidget(right)
        splitter.setSizes([280, 700])

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._run)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._run)

        self._load_indices()

    # --- index listesi ---

    def _load_indices(self) -> None:
        self._status.setText("Index'ler yükleniyor…")

        def done(rows):
            self._indices.clear()
            for row in rows:
                name = row.get("index", "")
                docs = row.get("docs.count", "?")
                health = row.get("health", "")
                item = QListWidgetItem(f"{name}\n{health} · {docs} doc")
                item.setData(_INDEX_ROLE, name)
                self._indices.addItem(item)
            self._status.setText(f"{len(rows)} index")

        run_in_background(self._pool, self._agent.list_indices, on_result=done, on_error=self._error)

    def _on_index_selected(self) -> None:
        item = self._indices.currentItem()
        if item is None:
            return
        self._current_index = item.data(_INDEX_ROLE)
        self._index_label.setText(f"index: {self._current_index}")

    # --- mapping ---

    def _show_mapping(self) -> None:
        if not self._current_index:
            QMessageBox.information(self, "Index seç", "Önce soldan bir index seç.")
            return
        index = self._current_index
        self._status.setText("Mapping yükleniyor…")

        def done(mapping):
            self._result.setPlainText(json.dumps(mapping, indent=2, ensure_ascii=False))
            self._status.setText(f"{index} mapping")

        run_in_background(
            self._pool, self._agent.get_mapping, args=(index,),
            on_result=done, on_error=self._error,
        )

    # --- query ---

    def _run(self) -> None:
        if not self._current_index:
            QMessageBox.information(self, "Index seç", "Önce soldan bir index seç.")
            return
        dsl = self._editor.toPlainText()
        index = self._current_index
        size = self._size.value()
        self._run_btn.setEnabled(False)
        self._status.setText("Çalışıyor…")

        def done(payload):
            data, total, took = payload
            hits = data.get("hits", {}).get("hits", [])
            sources = [h.get("_source", h) for h in hits]
            self._result.setPlainText(json.dumps(sources, indent=2, ensure_ascii=False))
            self._status.setText(f"{len(hits)} / {total} hit · {took} ms")

        def finished():
            self._run_btn.setEnabled(True)

        run_in_background(
            self._pool, self._agent.search, args=(index, dsl, size),
            on_result=done, on_error=self._query_error, on_finished=finished,
        )

    def _error(self, exc: Exception) -> None:
        self._status.setText("Hata")
        QMessageBox.critical(self, "Elasticsearch hatası", str(exc))

    def _query_error(self, exc: Exception) -> None:
        self._status.setText("Sorgu hatası")
        self._result.setPlainText(str(exc))

    def close_agent(self) -> None:
        self._agent.close()
