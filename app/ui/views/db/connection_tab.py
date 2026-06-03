"""Tek bir aktif MySQL bağlantısının çalışma alanı.

Sol: schema tree (databases → tables → columns, lazy yükleme).
Sağ: çoklu sorgu sekmesi (QueryTab) — her tablo/sorgu ayrı sekmede açılır.
Tüm IO işleri arka plan thread'inde çalışır; UI donmaz.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.db_agent import MySQLAgent, QueryResult
from app.models.connection_profile import ConnectionProfile
from app.services.worker import run_in_background

_NODE_ROLE = Qt.ItemDataRole.UserRole       # ("db", name) | ("table", db, table) | ("loading",)


class QueryTab(QWidget):
    """Tek bir SQL editör + sonuç tablosu çalışma alanı."""

    def __init__(self, agent: MySQLAgent, threadpool, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._agent = agent
        self._pool = threadpool
        self._running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        self._run_btn = QPushButton("▶ Çalıştır")
        self._run_btn.clicked.connect(self.run)
        toolbar.addWidget(self._run_btn)
        toolbar.addWidget(QLabel("Maks satır:"))
        self._max_rows = QSpinBox()
        self._max_rows.setRange(1, 100000)
        self._max_rows.setValue(1000)
        toolbar.addWidget(self._max_rows)
        toolbar.addStretch(1)
        self._status = QLabel("Read-only · hazır")
        self._status.setObjectName("PanelLabel")
        toolbar.addWidget(self._status)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("SELECT * FROM ...   (Ctrl+Enter ile çalıştır)")
        splitter.addWidget(self._editor)
        self._result = QTableWidget()
        self._result.setAlternatingRowColors(True)
        self._result.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        splitter.addWidget(self._result)
        splitter.setSizes([170, 360])
        layout.addWidget(splitter, 1)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.run)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.run)

    def set_sql(self, sql: str) -> None:
        self._editor.setPlainText(sql)

    def run(self) -> None:
        if self._running:
            return
        sql = self._editor.toPlainText().strip()
        if not sql:
            return
        self._running = True
        self._run_btn.setEnabled(False)
        self._status.setText("Çalışıyor…")

        def done(result: QueryResult):
            self._populate(result)

        def finished():
            self._running = False
            self._run_btn.setEnabled(True)

        run_in_background(
            self._pool, self._agent.run_query,
            args=(sql, self._max_rows.value()),
            on_result=done, on_error=self._show_error, on_finished=finished,
        )

    def _populate(self, result: QueryResult) -> None:
        self._result.clear()
        self._result.setColumnCount(len(result.columns))
        self._result.setHorizontalHeaderLabels(result.columns)
        self._result.setRowCount(len(result.rows))
        for r, row in enumerate(result.rows):
            for c, value in enumerate(row):
                text = "NULL" if value is None else str(value)
                self._result.setItem(r, c, QTableWidgetItem(text))
        self._result.resizeColumnsToContents()

        status = f"{result.rowcount} satır · {result.execution_ms:.0f} ms"
        if result.truncated:
            status += f" · ilk {self._max_rows.value()} (kesildi)"
        self._status.setText(status)

    def _show_error(self, exc: Exception) -> None:
        self._status.setText("Sorgu hatası")
        QMessageBox.critical(self, "Sorgu hatası", str(exc))


class DbConnectionTab(QWidget):
    def __init__(
        self,
        agent: MySQLAgent,
        profile: ConnectionProfile,
        threadpool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._agent = agent
        self._profile = profile
        self._pool = threadpool
        self._query_counter = 0

        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        # --- sol: schema tree ---
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Şema")
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        splitter.addWidget(self._tree)

        # --- sağ: çoklu sorgu sekmeleri ---
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        topbar = QHBoxLayout()
        new_query_btn = QPushButton("+ Yeni sorgu")
        new_query_btn.setObjectName("Ghost")
        new_query_btn.clicked.connect(lambda: self.open_query(autorun=False))
        topbar.addWidget(new_query_btn)
        topbar.addStretch(1)
        right_layout.addLayout(topbar)

        self._query_tabs = QTabWidget()
        self._query_tabs.setTabsClosable(True)
        self._query_tabs.setMovable(True)
        self._query_tabs.tabCloseRequested.connect(self._close_query)
        right_layout.addWidget(self._query_tabs, 1)

        splitter.addWidget(right)
        splitter.setSizes([260, 720])

        self._load_databases()
        self.open_query(autorun=False)   # başlangıçta boş bir sorgu sekmesi

    # --- çoklu sorgu sekmeleri ---

    def open_query(
        self, sql: Optional[str] = None, title: Optional[str] = None, autorun: bool = False
    ) -> None:
        self._query_counter += 1
        tab = QueryTab(self._agent, self._pool)
        if sql:
            tab.set_sql(sql)
        label = title or f"Sorgu {self._query_counter}"
        index = self._query_tabs.addTab(tab, label)
        self._query_tabs.setCurrentIndex(index)
        if autorun:
            tab.run()

    def _close_query(self, index: int) -> None:
        widget = self._query_tabs.widget(index)
        self._query_tabs.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        # Tüm sekmeler kapandıysa sayacı sıfırla; sonraki sorgu "Sorgu 1"den başlar
        # (eskiden son sekme kapatılınca otomatik yenisi açılıp no sürekli artıyordu).
        if self._query_tabs.count() == 0:
            self._query_counter = 0

    # --- schema tree ---

    def _load_databases(self) -> None:
        def done(dbs):
            self._tree.clear()
            for db in dbs:
                item = QTreeWidgetItem([db])
                item.setData(0, _NODE_ROLE, ("db", db))
                self._add_loading_child(item)
                self._tree.addTopLevelItem(item)
            default_db = self._profile.extra.get("database")
            if default_db:
                self._expand_db(default_db)

        run_in_background(
            self._pool, self._agent.list_databases,
            on_result=done, on_error=self._show_error,
        )

    def _expand_db(self, db_name: str) -> None:
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, _NODE_ROLE) == ("db", db_name):
                item.setExpanded(True)
                break

    def _add_loading_child(self, parent: QTreeWidgetItem) -> None:
        loading = QTreeWidgetItem(["yükleniyor…"])
        loading.setData(0, _NODE_ROLE, ("loading",))
        parent.addChild(loading)

    def _is_unloaded(self, item: QTreeWidgetItem) -> bool:
        return (
            item.childCount() == 1
            and item.child(0).data(0, _NODE_ROLE) == ("loading",)
        )

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        if not self._is_unloaded(item):
            return
        node = item.data(0, _NODE_ROLE)
        if node[0] == "db":
            self._load_tables(item, node[1])
        elif node[0] == "table":
            self._load_columns(item, node[1], node[2])

    def _load_tables(self, db_item: QTreeWidgetItem, db: str) -> None:
        def done(tables):
            db_item.takeChildren()
            for t in tables:
                child = QTreeWidgetItem([t])
                child.setData(0, _NODE_ROLE, ("table", db, t))
                self._add_loading_child(child)
                db_item.addChild(child)

        run_in_background(
            self._pool, self._agent.list_tables,
            args=(db,), on_result=done, on_error=self._show_error,
        )

    def _load_columns(self, table_item: QTreeWidgetItem, db: str, table: str) -> None:
        def done(columns):
            table_item.takeChildren()
            for col in columns:
                label = f"{col.name}  ·  {col.type}"
                if col.key == "PRI":
                    label += "  🔑"
                child = QTreeWidgetItem([label])
                child.setData(0, _NODE_ROLE, ("column", db, table, col.name))
                table_item.addChild(child)

        run_in_background(
            self._pool, self._agent.get_columns,
            args=(db, table), on_result=done, on_error=self._show_error,
        )

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        node = item.data(0, _NODE_ROLE)
        if node and node[0] == "table":
            _, db, table = node
            sql = f"SELECT * FROM `{db}`.`{table}` LIMIT 100"
            self.open_query(sql=sql, title=table, autorun=True)

    def _show_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "Hata", str(exc))

    # --- yaşam döngüsü ---

    def close_agent(self) -> None:
        self._agent.close()
