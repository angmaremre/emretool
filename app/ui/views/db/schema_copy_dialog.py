"""Schema kopyalama dialog'u — kaynak şemayı hedef bağlantıya datalı/datasız kopyalar."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, Qt, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.db_agent import MySQLAgent
from app.core.schema_copy import SchemaCopier
from app.models.connection_profile import ConnectionProfile
from app.services.storage import Storage
from app.services.worker import run_in_background
from app.ui.views.db.profile_config import MODULE, build_mysql_config

_PROFILE_ROLE = Qt.ItemDataRole.UserRole


class _CopyProgress(QObject):
    """İlerleme mesajlarını thread'ler arası güvenle UI'ye taşır."""

    message = pyqtSignal(str)


class SchemaCopyDialog(QDialog):
    def __init__(self, storage: Storage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._storage = storage
        self._running = False
        self.setWindowTitle("Schema Kopyala")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        form = QFormLayout()

        # --- kaynak ---
        self._source_combo = QComboBox()
        source_row = QHBoxLayout()
        source_row.addWidget(self._source_combo, 1)
        load_btn = QPushButton("Şemaları yükle")
        load_btn.setObjectName("Ghost")
        load_btn.clicked.connect(self._load_source_schemas)
        source_row.addWidget(load_btn)
        source_w = QWidget()
        source_w.setLayout(source_row)
        form.addRow("Kaynak bağlantı", source_w)

        self._source_schema = QComboBox()
        self._source_schema.currentTextChanged.connect(self._on_source_schema_changed)
        form.addRow("Kaynak şema", self._source_schema)

        # --- hedef ---
        self._target_combo = QComboBox()
        form.addRow("Hedef bağlantı", self._target_combo)

        self._target_schema = QLineEdit()
        self._target_schema.setPlaceholderText("(hedef şema adı)")
        form.addRow("Hedef şema", self._target_schema)

        self._include_data = QCheckBox("Veriyle birlikte kopyala")
        form.addRow("", self._include_data)

        root.addLayout(form)

        # --- ilerleme ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        root.addWidget(self._progress)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("İlerleme burada görünecek…")
        root.addWidget(self._log, 1)

        # --- butonlar ---
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._copy_btn = QPushButton("Kopyala")
        self._copy_btn.clicked.connect(self._start_copy)
        close_btn = QPushButton("Kapat")
        close_btn.setObjectName("Ghost")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        btn_row.addWidget(self._copy_btn)
        root.addLayout(btn_row)

        self._populate_profiles()

    # --- profiller ---

    def _populate_profiles(self) -> None:
        profiles = self._storage.list_profiles(MODULE)
        for combo in (self._source_combo, self._target_combo):
            combo.clear()
            for p in profiles:
                combo.addItem(f"{p.name}  ({p.host})", p)
        if not profiles:
            self._log.appendPlainText(
                "Önce en az bir Database bağlantısı tanımlamalısın."
            )
            self._copy_btn.setEnabled(False)

    def _selected_profile(self, combo: QComboBox) -> Optional[ConnectionProfile]:
        return combo.currentData()

    # --- kaynak şemaları yükle ---

    def _load_source_schemas(self) -> None:
        profile = self._selected_profile(self._source_combo)
        if profile is None:
            return
        self._log.appendPlainText(f"'{profile.name}' şemaları yükleniyor…")
        agent = MySQLAgent(build_mysql_config(profile))

        def done(dbs):
            agent.close()
            self._source_schema.clear()
            self._source_schema.addItems(dbs)
            self._log.appendPlainText(f"{len(dbs)} şema yüklendi.")

        def err(exc: Exception):
            agent.close()
            QMessageBox.critical(self, "Hata", f"Şemalar yüklenemedi:\n{exc}")

        def run():
            agent.connect()
            return agent.list_databases()

        run_in_background(
            QThreadPool.globalInstance(), run, on_result=done, on_error=err
        )

    def _on_source_schema_changed(self, text: str) -> None:
        if text and not self._target_schema.text().strip():
            self._target_schema.setText(text)

    # --- kopyalama ---

    def _start_copy(self) -> None:
        if self._running:
            return
        source = self._selected_profile(self._source_combo)
        target = self._selected_profile(self._target_combo)
        source_schema = self._source_schema.currentText().strip()
        target_schema = self._target_schema.text().strip()

        if not (source and target and source_schema and target_schema):
            QMessageBox.warning(
                self, "Eksik bilgi",
                "Kaynak/hedef bağlantı ve şema adlarını doldur.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Onay",
            f"'{source.name}' → '{source_schema}' şeması\n"
            f"'{target.name}' → '{target_schema}' hedefine "
            f"{'veriyle' if self._include_data.isChecked() else 'şema olarak'} "
            f"kopyalanacak.\n\nHedefte aynı isimli tablolar DROP edilecek. Devam?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        copier = SchemaCopier(
            source_cfg=build_mysql_config(source),
            target_cfg=build_mysql_config(target),
            source_schema=source_schema,
            target_schema=target_schema,
            include_data=self._include_data.isChecked(),
        )

        progress = _CopyProgress()
        progress.message.connect(self._log.appendPlainText)

        self._running = True
        self._copy_btn.setEnabled(False)
        self._progress.setRange(0, 0)   # belirsiz (çalışıyor)
        self._log.appendPlainText("— Kopyalama başladı —")

        def err(exc: Exception):
            self._log.appendPlainText(f"HATA: {exc}")
            QMessageBox.critical(self, "Kopyalama hatası", str(exc))

        def finished():
            self._running = False
            self._copy_btn.setEnabled(True)
            self._progress.setRange(0, 1)
            self._progress.setValue(1)

        run_in_background(
            QThreadPool.globalInstance(),
            copier.run,
            args=(progress.message.emit,),
            on_error=err,
            on_finished=finished,
        )
