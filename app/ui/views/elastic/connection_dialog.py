"""Elasticsearch bağlantı profili dialog'u (host/port/scheme/auth + SSH + test)."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.db_agent import SSHConfig
from app.core.elastic_agent import ElasticAgent, ElasticConfig
from app.models.connection_profile import ConnectionProfile
from app.services import secrets
from app.services.storage import Storage
from app.services.worker import run_in_background
from app.ui.views.elastic.profile_config import MODULE, ssh_account
from app.ui.widgets.fields import PasswordField


class ElasticConnectionDialog(QDialog):
    def __init__(
        self,
        storage: Storage,
        profile: Optional[ConnectionProfile] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._storage = storage
        self._profile = profile
        self.saved_profile: Optional[ConnectionProfile] = None
        self.setWindowTitle(
            "Elasticsearch Bağlantı Düzenle" if profile else "Yeni Elasticsearch Bağlantısı"
        )
        self.setMinimumWidth(540)

        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._name = QLineEdit()
        self._host = QLineEdit("localhost")
        self._host.setToolTip(
            "Sade ad (localhost), host:port veya tam URL (https://host:9243) yazabilirsiniz."
        )
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(9200)
        self._scheme = QComboBox()
        self._scheme.addItems(["http", "https"])
        self._user = QLineEdit()
        self._user.setPlaceholderText("(opsiyonel)")
        self._password = PasswordField()
        self._verify = QCheckBox("TLS sertifikasını doğrula")

        form.addRow("Ad", self._name)
        form.addRow("Host", self._host)
        form.addRow("Port", self._port)
        form.addRow("Şema", self._scheme)
        form.addRow("Kullanıcı", self._user)
        form.addRow("Şifre", self._password)
        form.addRow("", self._verify)
        root.addLayout(form)

        self._use_ssh = QCheckBox("SSH tüneli üzerinden bağlan")
        root.addWidget(self._use_ssh)
        self._ssh_group = QGroupBox("SSH ayarları")
        ssh_form = QFormLayout(self._ssh_group)
        ssh_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._ssh_host = QLineEdit()
        self._ssh_port = QSpinBox()
        self._ssh_port.setRange(1, 65535)
        self._ssh_port.setValue(22)
        self._ssh_user = QLineEdit()
        self._ssh_password = PasswordField()
        pkey_row = QHBoxLayout()
        self._ssh_pkey = QLineEdit()
        self._ssh_pkey.setPlaceholderText("(opsiyonel private key dosyası)")
        browse = QPushButton("Gözat")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse_pkey)
        pkey_row.addWidget(self._ssh_pkey)
        pkey_row.addWidget(browse)
        pkey_w = QWidget()
        pkey_w.setLayout(pkey_row)
        ssh_form.addRow("SSH Host", self._ssh_host)
        ssh_form.addRow("SSH Port", self._ssh_port)
        ssh_form.addRow("SSH Kullanıcı", self._ssh_user)
        ssh_form.addRow("SSH Şifre", self._ssh_password)
        ssh_form.addRow("Private Key", pkey_w)
        root.addWidget(self._ssh_group)
        self._use_ssh.toggled.connect(self._ssh_group.setVisible)
        self._ssh_group.setVisible(False)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._test_btn = QPushButton("Bağlantıyı test et")
        self._test_btn.setObjectName("Ghost")
        self._test_btn.clicked.connect(self._test)
        buttons.addButton(self._test_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if profile is not None:
            self._load(profile)

    def _browse_pkey(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Private key seç")
        if path:
            self._ssh_pkey.setText(path)

    def _load(self, profile: ConnectionProfile) -> None:
        self._name.setText(profile.name)
        self._host.setText(profile.host)
        self._port.setValue(int(profile.port or 9200))
        self._user.setText(profile.username)
        extra = profile.extra
        self._scheme.setCurrentText(extra.get("scheme", "http"))
        self._verify.setChecked(bool(extra.get("verify_certs", False)))
        if profile.id is not None and profile.username:
            pw = secrets.get_password(MODULE, profile.id, profile.username)
            if pw:
                self._password.setText(pw)
        if extra.get("use_ssh"):
            self._use_ssh.setChecked(True)
            self._ssh_host.setText(extra.get("ssh_host", ""))
            self._ssh_port.setValue(int(extra.get("ssh_port", 22) or 22))
            self._ssh_user.setText(extra.get("ssh_user", ""))
            self._ssh_pkey.setText(extra.get("ssh_pkey_path", ""))
            if profile.id is not None:
                ssh_pw = secrets.get_password(
                    MODULE, profile.id, ssh_account(extra.get("ssh_user", ""))
                )
                if ssh_pw:
                    self._ssh_password.setText(ssh_pw)

    def _config_from_form(self) -> ElasticConfig:
        ssh = None
        if self._use_ssh.isChecked():
            ssh = SSHConfig(
                host=self._ssh_host.text().strip(),
                port=self._ssh_port.value(),
                username=self._ssh_user.text().strip(),
                password=self._ssh_password.text() or None,
                pkey_path=self._ssh_pkey.text().strip() or None,
            )
        return ElasticConfig(
            host=self._host.text().strip() or "localhost",
            port=self._port.value(),
            scheme=self._scheme.currentText(),
            username=self._user.text().strip() or None,
            password=self._password.text() or None,
            verify_certs=self._verify.isChecked(),
            ssh=ssh,
        )

    def _test(self) -> None:
        agent = ElasticAgent(self._config_from_form())
        self._test_btn.setEnabled(False)
        self._test_btn.setText("Test ediliyor…")

        def ok(_):
            agent.close()
            QMessageBox.information(self, "Bağlantı testi", "Bağlantı başarılı ✓")

        def err(exc: Exception):
            agent.close()
            QMessageBox.critical(self, "Bağlantı testi", f"Bağlanılamadı:\n{exc}")

        def finished():
            self._test_btn.setEnabled(True)
            self._test_btn.setText("Bağlantıyı test et")

        run_in_background(
            QThreadPool.globalInstance(), agent.connect,
            on_result=ok, on_error=err, on_finished=finished,
        )

    def _on_save(self) -> None:
        name = self._name.text().strip() or self._host.text().strip()
        extra = {
            "scheme": self._scheme.currentText(),
            "verify_certs": self._verify.isChecked(),
        }
        use_ssh = self._use_ssh.isChecked()
        extra["use_ssh"] = use_ssh
        if use_ssh:
            extra["ssh_host"] = self._ssh_host.text().strip()
            extra["ssh_port"] = self._ssh_port.value()
            extra["ssh_user"] = self._ssh_user.text().strip()
            extra["ssh_pkey_path"] = self._ssh_pkey.text().strip()

        profile = self._profile or ConnectionProfile(module=MODULE, name=name)
        profile.name = name
        profile.host = self._host.text().strip() or "localhost"
        profile.port = self._port.value()
        profile.username = self._user.text().strip()
        profile.extra = extra

        profile_id = self._storage.save_profile(profile)
        if profile.username:
            secrets.set_password(MODULE, profile_id, profile.username, self._password.text())
        if use_ssh:
            secrets.set_password(
                MODULE, profile_id, ssh_account(extra["ssh_user"]), self._ssh_password.text()
            )
        self.saved_profile = profile
        self.accept()
