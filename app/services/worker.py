"""Arka plan iş çalıştırma — UI thread'inin (event loop) donmasını engeller.

Ağ/IO işleri (DB sorgusu, Redis tarama, ES isteği) QThreadPool üzerinde çalışır;
sonuç sinyaller aracılığıyla UI thread'ine güvenle geri döner.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    result = pyqtSignal(object)      # başarılı sonuç (dönüş değeri)
    error = pyqtSignal(object)       # yakalanan Exception örneği
    finished = pyqtSignal()


class Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 — UI'ye iletmek için bilinçli yakalama
            self.signals.error.emit(exc)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


def run_in_background(
    pool: QThreadPool,
    fn: Callable[..., Any],
    *,
    on_result: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    on_finished: Optional[Callable[[], None]] = None,
    args: tuple = (),
    kwargs: Optional[dict] = None,
) -> Worker:
    """``fn``'i thread pool'da çalıştırır; callback'leri sinyallere bağlar."""
    worker = Worker(fn, *args, **(kwargs or {}))
    if on_result is not None:
        worker.signals.result.connect(on_result)
    if on_error is not None:
        worker.signals.error.connect(on_error)
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)
    pool.start(worker)
    return worker
