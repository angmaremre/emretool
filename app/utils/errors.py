"""Global hata yakalama.

PyQt6'da bir slot/callback (sinyal alıcısı) içinde yakalanmamış bir Python
exception'ı, varsayılan ``sys.excepthook`` ile birlikte uygulamayı ``qFatal``
ile **abort** ettirir — yani pencere bir anda kapanır. Burada özel bir
excepthook kurarak bunu engelliyoruz: hata bir dosyaya loglanır ve kullanıcıya
bir dialog ile gösterilir; uygulama çalışmaya devam eder.
"""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.utils.paths import app_data_dir

_log = logging.getLogger("emretool")
_in_hook = False  # iç içe (recursive) dialog/log çağrısını engelle


def _setup_logging() -> Path:
    log_path = app_data_dir() / "emretool.log"
    if not _log.handlers:
        handler = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        _log.setLevel(logging.INFO)
        _log.addHandler(handler)
    return log_path


def install_excepthook() -> Path:
    """Global excepthook'u kurar; log dosyasının yolunu döndürür."""
    log_path = _setup_logging()

    def hook(exc_type, exc, tb) -> None:
        global _in_hook
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        _log.error("Yakalanmamis hata:\n%s", text)
        if _in_hook:  # hook içinde tekrar hata olursa sonsuz döngüye girme
            return
        _in_hook = True
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                box = QMessageBox()
                box.setIcon(QMessageBox.Icon.Critical)
                box.setWindowTitle("Beklenmeyen hata")
                box.setText(
                    "Bir hata oluştu, ancak uygulama çalışmaya devam ediyor."
                )
                box.setInformativeText(f"{exc_type.__name__}: {exc}")
                box.setDetailedText(text)
                box.exec()
        except Exception:  # noqa: BLE001 — hook asla patlamamalı
            pass
        finally:
            _in_hook = False

    sys.excepthook = hook
    return log_path
