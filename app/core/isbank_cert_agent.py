"""İşbank sertifika üretimi — yerel ``openssl``/``keytool`` çağıran iş mantığı.

Bağlantı yok; UI'dan bağımsız, tamamen yerel CLI araçlarını çalıştırıp seçilen
klasörde dosya üretir. ``schema_copy.py``'deki subprocess desenini örnek alır:
binary'ler PATH + fallback dizinlerde aranır, sırlar argv'ye YAZILMAZ (openssl'e
``-passin``/``-passout env:…``, keytool'a ``-storepass:env`` ile geçilir), böylece
``ps`` çıktısında görünmez.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from typing import List, Optional, Tuple

_BINARY_DIRS = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
]

_DEFAULT_TIMEOUT = 120


def _find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    dirs = list(_BINARY_DIRS)
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        dirs.insert(0, os.path.join(java_home, "bin"))
    for directory in dirs:
        candidate = os.path.join(directory, name)
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError(
        f"'{name}' bulunamadı. Kurulu olduğundan ve PATH'te olduğundan emin olun."
    )


def _build_subject(subject: dict) -> str:
    """{'C':'TR', ...} → '/C=TR/ST=…/O=…/CN=…' (boş alanlar atlanır)."""
    order = ["C", "ST", "L", "O", "OU", "CN"]
    parts = []
    for key in order:
        value = str(subject.get(key, "")).strip()
        if value:
            parts.append(f"{key}={value}")
    return "/" + "/".join(parts)


class CertManager:
    """openssl/keytool adımlarını çalıştırır; her metot log'a basılacak metin döner."""

    # --- düşük seviye ---

    def _run(
        self,
        cmd: List[str],
        *,
        env_extra: Optional[dict] = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> subprocess.CompletedProcess:
        env = None
        if env_extra:
            env = {**os.environ, **env_extra}
        try:
            result = subprocess.run(
                cmd, capture_output=True, env=env, timeout=timeout
            )
        except FileNotFoundError as exc:  # binary çalıştırılamadı
            raise RuntimeError(str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Komut zaman aşımına uğradı: {' '.join(cmd)}") from exc
        if result.returncode != 0:
            msg = result.stderr.decode(errors="replace").strip() or "bilinmeyen hata"
            raise RuntimeError(msg)
        return result

    @staticmethod
    def _fmt(cmd: List[str], output: str = "") -> str:
        """Log satırı: çalıştırılan komut (+ varsa çıktı). Argv sır içermez."""
        line = "$ " + " ".join(cmd)
        out = output.strip()
        return f"{line}\n{out}" if out else line

    # --- adımlar ---

    def gen_key(
        self, folder: str, key_name: str, bits: int, encrypt: bool, passphrase: str
    ) -> str:
        """Adım 1: private key üret (isteğe bağlı -aes256 ile şifreli)."""
        openssl = _find_binary("openssl")
        out_path = os.path.join(folder, key_name)
        cmd = [openssl, "genrsa"]
        env_extra = None
        if encrypt:
            if not passphrase:
                raise RuntimeError("Şifreli key için passphrase gerekli.")
            cmd += ["-aes256", "-passout", "env:PW"]
            env_extra = {"PW": passphrase}
        cmd += ["-out", out_path, str(bits)]
        result = self._run(cmd, env_extra=env_extra)
        note = " (şifreli)" if encrypt else " (şifresiz)"
        return self._fmt(cmd, result.stderr.decode(errors="replace")) + (
            f"\n✓ Private key üretildi{note}: {out_path}"
        )

    def gen_csr(
        self,
        folder: str,
        key_name: str,
        csr_name: str,
        subject: dict,
        passphrase: str,
    ) -> str:
        """Adım 2: CSR üret (subject alanlarıyla)."""
        openssl = _find_binary("openssl")
        key_path = os.path.join(folder, key_name)
        csr_path = os.path.join(folder, csr_name)
        if not os.path.exists(key_path):
            raise RuntimeError(f"Key bulunamadı: {key_path}")
        subj = _build_subject(subject)
        cmd = [openssl, "req", "-new", "-key", key_path, "-out", csr_path, "-subj", subj]
        env_extra = None
        if passphrase:
            cmd += ["-passin", "env:PW"]
            env_extra = {"PW": passphrase}
        self._run(cmd, env_extra=env_extra)
        return self._fmt(cmd) + f"\n✓ CSR üretildi: {csr_path}"

    def inspect_csr(self, folder: str, csr_name: str) -> str:
        """Adım 3: CSR içeriğini metin olarak göster."""
        openssl = _find_binary("openssl")
        csr_path = os.path.join(folder, csr_name)
        if not os.path.exists(csr_path):
            raise RuntimeError(f"CSR bulunamadı: {csr_path}")
        cmd = [openssl, "req", "-in", csr_path, "-noout", "-text"]
        result = self._run(cmd)
        return self._fmt(cmd, result.stdout.decode(errors="replace"))

    def verify_match(
        self, cert_path: str, key_path: str, key_passphrase: str
    ) -> Tuple[bool, str, str, str]:
        """Adım 5: sertifika ile key'in modulus md5'lerini karşılaştır.

        (eslesti, cert_md5, key_md5, log) döndürür.
        """
        openssl = _find_binary("openssl")
        if not os.path.exists(cert_path):
            raise RuntimeError(f"Sertifika bulunamadı: {cert_path}")
        if not os.path.exists(key_path):
            raise RuntimeError(f"Key bulunamadı: {key_path}")

        cert_cmd = [openssl, "x509", "-noout", "-modulus", "-in", cert_path]
        cert_out = self._run(cert_cmd).stdout

        key_cmd = [openssl, "rsa", "-noout", "-modulus", "-in", key_path]
        env_extra = None
        if key_passphrase:
            key_cmd += ["-passin", "env:PW"]
            env_extra = {"PW": key_passphrase}
        key_out = self._run(key_cmd, env_extra=env_extra).stdout

        cert_md5 = hashlib.md5(cert_out).hexdigest()
        key_md5 = hashlib.md5(key_out).hexdigest()
        matched = cert_md5 == key_md5
        symbol = "✓ EŞLEŞTİ" if matched else "✗ EŞLEŞMEDİ"
        log = (
            self._fmt(cert_cmd) + "\n"
            + self._fmt(key_cmd) + "\n"
            + f"cert modulus md5: {cert_md5}\n"
            + f"key  modulus md5: {key_md5}\n"
            + symbol
        )
        return matched, cert_md5, key_md5, log

    def export_p12(
        self,
        cert_path: str,
        key_path: str,
        out_path: str,
        name: str,
        ca_path: str,
        caname: str,
        key_passphrase: str,
        p12_password: str,
    ) -> str:
        """Adım 6/7: cert + key'den .p12 üret (CA zinciriyle)."""
        openssl = _find_binary("openssl")
        for label, path in (("Sertifika", cert_path), ("Key", key_path)):
            if not os.path.exists(path):
                raise RuntimeError(f"{label} bulunamadı: {path}")
        cmd = [
            openssl, "pkcs12", "-export",
            "-in", cert_path,
            "-inkey", key_path,
            "-out", out_path,
        ]
        if name:
            cmd += ["-name", name]
        if ca_path:
            if not os.path.exists(ca_path):
                raise RuntimeError(f"CA dosyası bulunamadı: {ca_path}")
            cmd += ["-CAfile", ca_path]
            if caname:
                cmd += ["-caname", caname]
        env_extra = {}
        if key_passphrase:
            cmd += ["-passin", "env:KEYPW"]
            env_extra["KEYPW"] = key_passphrase
        # p12 çıktı şifresi (boş olabilir)
        cmd += ["-passout", "env:P12PW"]
        env_extra["P12PW"] = p12_password or ""
        self._run(cmd, env_extra=env_extra)
        return self._fmt(cmd) + f"\n✓ P12 üretildi: {out_path}"

    def make_truststore(
        self, pem_path: str, keystore_path: str, alias: str, storepass: str
    ) -> str:
        """Adım 8: pem zincirinden PKCS12 truststore üret (keytool)."""
        keytool = _find_binary("keytool")
        if not os.path.exists(pem_path):
            raise RuntimeError(f"PEM dosyası bulunamadı: {pem_path}")
        if not storepass:
            raise RuntimeError("Truststore için storepass gerekli.")
        cmd = [
            keytool, "-importcert",
            "-alias", alias,
            "-file", pem_path,
            "-keystore", keystore_path,
            "-storetype", "PKCS12",
            "-storepass:env", "STOREPW",
            "-noprompt",
        ]
        result = self._run(cmd, env_extra={"STOREPW": storepass})
        out = result.stdout.decode(errors="replace") or result.stderr.decode(errors="replace")
        return self._fmt(cmd, out) + f"\n✓ Truststore üretildi: {keystore_path}"
