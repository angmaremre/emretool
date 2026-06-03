"""Modül (plugin) kayıt mekanizması.

Yeni bir modül eklemek için bir ``ModuleDescriptor`` üretip registry'ye kaydetmek
yeterlidir; sidebar ve ana pencere modülleri buradan okur. UI, somut view
sınıflarını bilmek zorunda kalmaz — ``view_factory`` üzerinden lazım oldukça üretir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, List

if TYPE_CHECKING:  # döngüsel import'tan kaçınmak için yalnızca tip denetiminde
    from PyQt6.QtWidgets import QWidget

    from app.core.container import ServiceContainer


@dataclass(frozen=True)
class ModuleDescriptor:
    key: str                                            # benzersiz anahtar: "database"
    title: str                                          # sidebar'da görünen ad
    icon: str                                           # şimdilik emoji/sembol
    order: int                                          # sidebar sıralaması
    view_factory: "Callable[[ServiceContainer], QWidget]"


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: Dict[str, ModuleDescriptor] = {}

    def register(self, descriptor: ModuleDescriptor) -> None:
        if descriptor.key in self._modules:
            raise ValueError(f"Modül zaten kayıtlı: {descriptor.key}")
        self._modules[descriptor.key] = descriptor

    def get(self, key: str) -> ModuleDescriptor:
        return self._modules[key]

    def modules(self) -> List[ModuleDescriptor]:
        return sorted(self._modules.values(), key=lambda m: (m.order, m.title))
