"""İşbank Sertifika Yönetimi modülü — klasör seç, adımları çalıştır, not tut.

Diğer modüllerin bağlantı/profil deseninden bilinçli olarak sapar: bu modülün
bağlantısı yoktur; yerel ``openssl``/``keytool`` çalıştırıp seçilen klasörde dosya
üretir. Ayarlar ve notlar seçilen klasörde saklanır (``isbank/project_io.py``).
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.isbank_cert_agent import CertManager
from app.services.worker import run_in_background
from app.ui.base_view import BaseModuleView
from app.ui.views.isbank import project_io
from app.ui.widgets.fields import PasswordField


class IsbankView(BaseModuleView):
    def __init__(self, container, parent: Optional[QWidget] = None) -> None:
        super().__init__(container, parent)
        self._cert = CertManager()
        self._loading = False  # programatik alan doldurma sırasında autosave'i bastır

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 520])

        self._apply_params(project_io._merged_defaults())

    # ------------------------------------------------------------------ UI

    def _build_left(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(4, 4, 4, 4)
        col.setSpacing(10)

        # Klasör
        folder_row = QHBoxLayout()
        self._folder = QLineEdit()
        self._folder.setReadOnly(True)
        self._folder.setPlaceholderText("Çıktı klasörü seç…")
        browse = QPushButton("Gözat")
        browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(QLabel("Klasör:"))
        folder_row.addWidget(self._folder, 1)
        folder_row.addWidget(browse)
        col.addLayout(folder_row)

        # Genel
        general = QGroupBox("Genel")
        gform = QFormLayout(general)
        gform.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._key_name = QLineEdit()
        self._csr_name = QLineEdit()
        self._bits = QSpinBox()
        self._bits.setRange(1024, 8192)
        self._bits.setSingleStep(1024)
        self._encrypt = QCheckBox("Şifreli (-aes256)")
        self._key_pw = PasswordField()
        gform.addRow("Key dosya adı", self._key_name)
        gform.addRow("CSR dosya adı", self._csr_name)
        gform.addRow("Anahtar uzunluğu", self._bits)
        gform.addRow("", self._encrypt)
        gform.addRow("Key passphrase", self._key_pw)
        warn = QLabel(
            "⚠ Passphrase bu klasördeki .isbank_cert.json içinde açık metin saklanır."
        )
        warn.setWordWrap(True)
        warn.setObjectName("Hint")
        gform.addRow("", warn)
        col.addWidget(general)

        # Subject
        subject = QGroupBox("CSR Subject (Flo resmi ünvanı)")
        sform = QFormLayout(subject)
        sform.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._subj: dict[str, QLineEdit] = {}
        labels = {
            "C": "Ülke (C)",
            "ST": "İl (ST)",
            "L": "Şehir (L)",
            "O": "Kuruluş (O)",
            "OU": "Birim (OU)",
            "CN": "Ortak Ad (CN)",
        }
        for key, label in labels.items():
            edit = QLineEdit()
            self._subj[key] = edit
            sform.addRow(label, edit)
        col.addWidget(subject)

        # Adımlar 1-3
        steps = QGroupBox("Üretim adımları")
        srow = QVBoxLayout(steps)
        self._btn_key = QPushButton("1. Private key üret")
        self._btn_key.clicked.connect(self._on_gen_key)
        self._btn_csr = QPushButton("2. CSR üret")
        self._btn_csr.clicked.connect(self._on_gen_csr)
        self._btn_inspect = QPushButton("3. CSR'ı kontrol et")
        self._btn_inspect.clicked.connect(self._on_inspect)
        for b in (self._btn_key, self._btn_csr, self._btn_inspect):
            srow.addWidget(b)
        info = QLabel(
            "4. CSR'ı bankaya yükleyin (Ticari İnternet Şubesi). Banka size "
            "client.cer ve CA zincirini (ca.crt) döner — bu adım manueldir."
        )
        info.setWordWrap(True)
        info.setObjectName("Hint")
        srow.addWidget(info)
        col.addWidget(steps)

        # Adım 5 — eşleşme
        verify = QGroupBox("5. Sertifika ↔ key eşleşmesi")
        vform = QFormLayout(verify)
        vform.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._verify_cert = QLineEdit()
        vform.addRow("Sertifika (client.cer)", self._file_row(self._verify_cert, "Sertifika seç"))
        self._btn_verify = QPushButton("Doğrula")
        self._btn_verify.clicked.connect(self._on_verify)
        self._verify_result = QLabel("")
        self._verify_result.setWordWrap(True)
        vform.addRow("", self._btn_verify)
        vform.addRow("Sonuç", self._verify_result)
        col.addWidget(verify)

        # P12
        p12 = QGroupBox("P12 üret (openssl pkcs12)")
        pform = QFormLayout(p12)
        pform.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._p12_cert = QLineEdit()
        self._p12_key = QLineEdit()
        self._p12_ca = QLineEdit()
        self._p12_name = QLineEdit()
        self._p12_out = QLineEdit()
        self._p12_caname = QLineEdit()
        self._p12_pw = PasswordField()
        pform.addRow("Sertifika (-in)", self._file_row(self._p12_cert, "Sertifika seç"))
        pform.addRow("Key (-inkey)", self._file_row(self._p12_key, "Key seç"))
        pform.addRow("CA dosyası (-CAfile)", self._file_row(self._p12_ca, "CA dosyası seç"))
        pform.addRow("İsim (-name)", self._p12_name)
        pform.addRow("caname", self._p12_caname)
        pform.addRow("Çıktı .p12 adı", self._p12_out)
        pform.addRow("P12 şifresi", self._p12_pw)
        self._btn_p12 = QPushButton("P12 üret")
        self._btn_p12.clicked.connect(self._on_p12)
        pform.addRow("", self._btn_p12)
        col.addWidget(p12)

        # Truststore
        ts = QGroupBox("8. Truststore (keytool)")
        tform = QFormLayout(ts)
        tform.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._ts_pem = QLineEdit()
        self._ts_out = QLineEdit()
        self._ts_alias = QLineEdit()
        self._ts_pw = PasswordField()
        tform.addRow("PEM zinciri (-file)", self._file_row(self._ts_pem, "PEM dosyası seç"))
        tform.addRow("Keystore çıktı adı", self._ts_out)
        tform.addRow("Alias", self._ts_alias)
        tform.addRow("storepass", self._ts_pw)
        self._btn_ts = QPushButton("Truststore oluştur")
        self._btn_ts.clicked.connect(self._on_truststore)
        tform.addRow("", self._btn_ts)
        col.addWidget(ts)

        col.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    def _build_right(self) -> QWidget:
        right = QSplitter(Qt.Orientation.Vertical)

        log_box = QWidget()
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("Çıktı"))
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Adımların komutları ve çıktısı burada görünecek…")
        log_layout.addWidget(self._log, 1)
        right.addWidget(log_box)

        notes_box = QWidget()
        notes_layout = QVBoxLayout(notes_box)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.addWidget(QLabel("Notlar (klasördeki NOTES.md'ye kaydedilir)"))
        self._notes = QPlainTextEdit()
        self._notes.setPlaceholderText("Süreç notları buraya…")
        self._notes.textChanged.connect(self._on_notes_changed)
        notes_layout.addWidget(self._notes, 1)
        right.addWidget(notes_box)

        right.setSizes([500, 300])
        return right

    def _file_row(self, edit: QLineEdit, title: str) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        btn = QPushButton("Gözat")
        btn.setObjectName("Ghost")
        btn.clicked.connect(lambda: self._browse_file(edit, title))
        row.addWidget(btn)
        return wrap

    # -------------------------------------------------------------- params

    def _collect_params(self) -> dict:
        return {
            "key_name": self._key_name.text().strip(),
            "csr_name": self._csr_name.text().strip(),
            "bits": self._bits.value(),
            "encrypt": self._encrypt.isChecked(),
            "key_passphrase": self._key_pw.text(),
            "subject": {k: e.text().strip() for k, e in self._subj.items()},
            "verify_cert": self._verify_cert.text().strip(),
            "p12_cert": self._p12_cert.text().strip(),
            "p12_key": self._p12_key.text().strip(),
            "p12_ca": self._p12_ca.text().strip(),
            "p12_name": self._p12_name.text().strip(),
            "p12_out": self._p12_out.text().strip(),
            "p12_caname": self._p12_caname.text().strip(),
            "p12_password": self._p12_pw.text(),
            "ts_pem": self._ts_pem.text().strip(),
            "ts_out": self._ts_out.text().strip(),
            "ts_alias": self._ts_alias.text().strip(),
            "ts_storepass": self._ts_pw.text(),
        }

    def _apply_params(self, data: dict) -> None:
        self._loading = True
        try:
            self._key_name.setText(data.get("key_name", ""))
            self._csr_name.setText(data.get("csr_name", ""))
            self._bits.setValue(int(data.get("bits", 2048)))
            self._encrypt.setChecked(bool(data.get("encrypt", True)))
            self._key_pw.setText(data.get("key_passphrase", ""))
            subject = data.get("subject", {})
            for k, edit in self._subj.items():
                edit.setText(subject.get(k, ""))
            self._verify_cert.setText(data.get("verify_cert", ""))
            self._p12_cert.setText(data.get("p12_cert", ""))
            self._p12_key.setText(data.get("p12_key", ""))
            self._p12_ca.setText(data.get("p12_ca", ""))
            self._p12_name.setText(data.get("p12_name", ""))
            self._p12_out.setText(data.get("p12_out", ""))
            self._p12_caname.setText(data.get("p12_caname", ""))
            self._p12_pw.setText(data.get("p12_password", ""))
            self._ts_pem.setText(data.get("ts_pem", ""))
            self._ts_out.setText(data.get("ts_out", ""))
            self._ts_alias.setText(data.get("ts_alias", ""))
            self._ts_pw.setText(data.get("ts_storepass", ""))
        finally:
            self._loading = False

    def _persist_params(self) -> None:
        folder = self._folder.text().strip()
        if folder:
            project_io.save_params(folder, self._collect_params())

    # ------------------------------------------------------------- actions

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Çıktı klasörü seç")
        if not path:
            return
        self._folder.setText(path)
        self._apply_params(project_io.load_params(path))
        self._loading = True
        try:
            self._notes.setPlainText(project_io.load_notes(path))
        finally:
            self._loading = False
        self._append_log(f"Klasör seçildi: {path}")

    def _browse_file(self, edit: QLineEdit, title: str) -> None:
        start = self._folder.text().strip() or ""
        path, _ = QFileDialog.getOpenFileName(self, title, start)
        if path:
            edit.setText(path)

    def _on_notes_changed(self) -> None:
        if self._loading:
            return
        folder = self._folder.text().strip()
        if folder:
            project_io.save_notes(folder, self._notes.toPlainText())

    def _confirm_overwrite(self, path: str) -> bool:
        """Dosya zaten varsa üzerine yazma onayı ister."""
        if os.path.exists(path):
            ans = QMessageBox.question(
                self,
                "Dosya mevcut",
                f"'{os.path.basename(path)}' zaten var. Üzerine yazılsın mı?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return ans == QMessageBox.StandardButton.Yes
        return True

    def _require_folder(self) -> Optional[str]:
        folder = self._folder.text().strip()
        if not folder:
            QMessageBox.information(self, "Klasör seç", "Önce bir çıktı klasörü seçin.")
            return None
        return folder

    def _append_log(self, text: str) -> None:
        self._log.appendPlainText(text)
        self._log.appendPlainText("")  # boş satır ayracı

    def _run(
        self,
        button: QPushButton,
        fn: Callable,
        args: tuple,
        on_ok: Callable,
    ) -> None:
        button.setEnabled(False)

        def error(exc: Exception) -> None:
            self._append_log(f"✗ Hata: {exc}")

        def finished() -> None:
            button.setEnabled(True)

        run_in_background(
            self.container.threadpool,
            fn,
            args=args,
            on_result=on_ok,
            on_error=error,
            on_finished=finished,
        )

    # --- adım handler'ları ---

    def _on_gen_key(self) -> None:
        folder = self._require_folder()
        if not folder:
            return
        p = self._collect_params()
        self._persist_params()
        if not p["key_name"]:
            QMessageBox.warning(self, "Eksik", "Key dosya adı boş olamaz.")
            return
        if not self._confirm_overwrite(os.path.join(folder, p["key_name"])):
            return
        self._run(
            self._btn_key,
            self._cert.gen_key,
            (folder, p["key_name"], p["bits"], p["encrypt"], p["key_passphrase"]),
            self._append_log,
        )

    def _on_gen_csr(self) -> None:
        folder = self._require_folder()
        if not folder:
            return
        p = self._collect_params()
        self._persist_params()
        if not p["csr_name"]:
            QMessageBox.warning(self, "Eksik", "CSR dosya adı boş olamaz.")
            return
        if not self._confirm_overwrite(os.path.join(folder, p["csr_name"])):
            return
        self._run(
            self._btn_csr,
            self._cert.gen_csr,
            (folder, p["key_name"], p["csr_name"], p["subject"], p["key_passphrase"]),
            self._append_log,
        )

    def _on_inspect(self) -> None:
        folder = self._require_folder()
        if not folder:
            return
        p = self._collect_params()
        self._run(
            self._btn_inspect,
            self._cert.inspect_csr,
            (folder, p["csr_name"]),
            self._append_log,
        )

    def _on_verify(self) -> None:
        folder = self._require_folder()
        if not folder:
            return
        p = self._collect_params()
        self._persist_params()
        cert = p["verify_cert"]
        if not cert:
            QMessageBox.warning(self, "Eksik", "Doğrulanacak sertifika dosyasını seçin.")
            return
        key_path = os.path.join(folder, p["key_name"])

        def on_ok(payload) -> None:
            matched, _c, _k, log = payload
            self._append_log(log)
            if matched:
                self._verify_result.setText("✓ EŞLEŞTİ")
                self._verify_result.setStyleSheet("color: #2e7d32; font-weight: bold;")
            else:
                self._verify_result.setText("✗ EŞLEŞMEDİ")
                self._verify_result.setStyleSheet("color: #c62828; font-weight: bold;")

        self._run(
            self._btn_verify,
            self._cert.verify_match,
            (cert, key_path, p["key_passphrase"]),
            on_ok,
        )

    def _on_p12(self) -> None:
        folder = self._require_folder()
        if not folder:
            return
        p = self._collect_params()
        self._persist_params()
        out_path = os.path.join(folder, p["p12_out"]) if p["p12_out"] else ""
        if not p["p12_cert"] or not p["p12_key"] or not out_path:
            QMessageBox.warning(self, "Eksik", "Sertifika, key ve çıktı adı zorunlu.")
            return
        if not self._confirm_overwrite(out_path):
            return
        self._run(
            self._btn_p12,
            self._cert.export_p12,
            (
                p["p12_cert"], p["p12_key"], out_path, p["p12_name"],
                p["p12_ca"], p["p12_caname"], p["key_passphrase"], p["p12_password"],
            ),
            self._append_log,
        )

    def _on_truststore(self) -> None:
        folder = self._require_folder()
        if not folder:
            return
        p = self._collect_params()
        self._persist_params()
        out_path = os.path.join(folder, p["ts_out"]) if p["ts_out"] else ""
        if not p["ts_pem"] or not out_path or not p["ts_alias"]:
            QMessageBox.warning(self, "Eksik", "PEM, çıktı adı ve alias zorunlu.")
            return
        if not self._confirm_overwrite(out_path):
            return
        self._run(
            self._btn_ts,
            self._cert.make_truststore,
            (p["ts_pem"], out_path, p["ts_alias"], p["ts_storepass"]),
            self._append_log,
        )
