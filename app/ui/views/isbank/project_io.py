"""Klasör-merkezli kalıcılık — proje ayarları ve notlar seçilen klasörde tutulur.

Uygulama SQLite'ına DOKUNULMAZ. Ayarlar ``.isbank_cert.json`` (passphrase dahil,
kullanıcı isteğiyle açık metin — 0600 izinli), notlar ``NOTES.md`` dosyasında.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

PARAMS_FILE = ".isbank_cert.json"
NOTES_FILE = "NOTES.md"

DEFAULTS: Dict[str, Any] = {
    "key_name": "flo_client.key",
    "csr_name": "flo_client.csr",
    "bits": 2048,
    "encrypt": True,
    "key_passphrase": "",
    "subject": {
        "C": "TR",
        "ST": "Istanbul",
        "L": "Istanbul",
        "O": "FLO MAGAZACILIK VE PAZARLAMA ANONIM SIRKETI",
        "OU": "IT",
        "CN": "FLO MAGAZACILIK VE PAZARLAMA ANONIM SIRKETI",
    },
    # P12 bölümü
    "p12_cert": "",
    "p12_key": "",
    "p12_ca": "",
    "p12_name": "flo-client-cert",
    "p12_out": "flo_client_certificate.p12",
    "p12_caname": "root",
    "p12_password": "",
    # Doğrulama (adım 5)
    "verify_cert": "",
    # Truststore (adım 8)
    "ts_pem": "",
    "ts_out": "truststore.p12",
    "ts_alias": "Isbank_Truststore",
    "ts_storepass": "",
}


def _merged_defaults() -> Dict[str, Any]:
    data = dict(DEFAULTS)
    data["subject"] = dict(DEFAULTS["subject"])
    return data


def load_params(folder: str) -> Dict[str, Any]:
    """``.isbank_cert.json`` varsa DEFAULTS üzerine bindirerek okur."""
    data = _merged_defaults()
    path = os.path.join(folder, PARAMS_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                subject = saved.pop("subject", None)
                data.update(saved)
                if isinstance(subject, dict):
                    data["subject"].update(subject)
        except (OSError, ValueError, json.JSONDecodeError):
            pass  # bozuk dosya → varsayılanlar
    return data


def save_params(folder: str, data: Dict[str, Any]) -> None:
    """Ayarları klasöre yazar (0600 — passphrase içerir)."""
    path = os.path.join(folder, PARAMS_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_notes(folder: str) -> str:
    path = os.path.join(folder, NOTES_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""
    return ""


def save_notes(folder: str, text: str) -> None:
    path = os.path.join(folder, NOTES_FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
