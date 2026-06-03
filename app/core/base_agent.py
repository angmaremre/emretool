"""Tüm modül agent'ları için ortak arayüz (data access katmanı).

Agent'lar UI'dan bağımsızdır; yalnızca bağlantı ve veri erişimiyle ilgilenir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        ...
