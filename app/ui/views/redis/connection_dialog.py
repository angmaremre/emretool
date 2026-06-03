"""Redis bağlantı profili dialog'u (host/port/db/şifre + opsiyonel SSH + test)."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import (
    QCheckBox,
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
from app.core.redis_agent import RedisAgent, RedisConfig
from app.models.connection_profile import ConnectionProfile
from app.services import secrets
from app.services.storage import Storage
from app.services.worker import run_in_background
from app.ui.views.redis.profile_config import MODULE, ssh_account


class RedisConnectionDialog(QDialog):
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
        self.setWindowTitle("Redis Bağlantı Düzenle" if profile else "Yeni Redis Bağlantısı")
        self.setMinimumWidth(440)

        root = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._host = QLineEdit("localhost")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(6379)
        self._db = QSpinBox()
        self._db.setRange(0, 255)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Ad", self._name)
        form.addRow("Host", self._host)
        form.addRow("Port", self._port)
        form.addRow("DB (index)", self._db)
        form.addRow("Şifre", self._password)
        root.addLayout(form)

        self._use_ssh = QCheckBox("SSH tüneli üzerinden bağlan")
        root.addWidget(self._use_ssh)
        self._ssh_group = QGroupBox("SSH ayarları")
        ssh_form = QFormLayout(self._ssh_group)
        self._ssh_host = QLineEdit()
        self._ssh_port = QSpinBox()
        self._ssh_port.setRange(1, 65535)
        self._ssh_port.setValue(22)
        self._ssh_user = QLineEdit()
        self._ssh_password = QLineEdit()
        self._ssh_password.setEchoMode(QLineEdit.EchoMode.Password)
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
        self._port.setValue(int(profile.port or 6379))
        extra = profile.extra
        self._db.setValue(int(extra.get("db", 0) or 0))
        if profile.id is not None:
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

    def _config_from_form(self) -> RedisConfig:
        ssh = None
        if self._use_ssh.isChecked():
            ssh = SSHConfig(
                host=self._ssh_host.text().strip(),
                port=self._ssh_port.value(),
                username=self._ssh_user.text().strip(),
                password=self._ssh_password.text() or None,
                pkey_path=self._ssh_pkey.text().strip() or None,
            )
        return RedisConfig(
            host=self._host.text().strip() or "localhost",
            port=self._port.value(),
            db=self._db.value(),
            password=self._password.text() or None,
            ssh=ssh,
        )

    def _test(self) -> None:
        agent = RedisAgent(self._config_from_form())
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
        extra = {"db": self._db.value()}
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
        profile.username = ""
        profile.extra = extra

        profile_id = self._storage.save_profile(profile)
        secrets.set_password(MODULE, profile_id, profile.username, self._password.text())
        if use_ssh:
            secrets.set_password(
                MODULE, profile_id, ssh_account(extra["ssh_user"]), self._ssh_password.text()
            )
        self.saved_profile = profile
        self.accept()
