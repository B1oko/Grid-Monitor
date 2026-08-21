from __future__ import annotations

import importlib
import pkgutil
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.drivers.base import DriverMeta, InverterDriver

_REGISTRY: dict[str, type[InverterDriver]] = {}
_LOADED = False


def register_driver(cls: type[InverterDriver]) -> type[InverterDriver]:
    driver_id = cls.meta.id
    existing = _REGISTRY.get(driver_id)
    if existing is not None and existing is not cls:
        raise ValueError(f"Duplicate driver id {driver_id!r}")
    _REGISTRY[driver_id] = cls
    return cls


def load_drivers() -> None:
    global _LOADED
    if _LOADED and _REGISTRY:
        return

    importlib.import_module("app.drivers.saj.h2")

    from app import drivers as package

    skip_suffixes = (".base", ".registry")
    for module_info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        name = module_info.name
        if name.endswith(skip_suffixes) or ".transports" in name:
            continue
        importlib.import_module(name)
    _LOADED = True


def get_driver_class(driver_id: str) -> type[InverterDriver]:
    load_drivers()
    try:
        return _REGISTRY[driver_id]
    except KeyError as exc:
        raise KeyError(f"Unknown inverter driver {driver_id!r}") from exc


def list_drivers() -> list[DriverMeta]:
    load_drivers()
    return [cls.meta for cls in _REGISTRY.values()]


def list_driver_classes() -> list[type[InverterDriver]]:
    load_drivers()
    return list(_REGISTRY.values())


def reset_registry() -> None:
    """Test helper: drop loaded driver modules so they can register again."""
    global _LOADED
    _REGISTRY.clear()
    _LOADED = False
    keep = {
        "app.drivers",
        "app.drivers.base",
        "app.drivers.registry",
        "app.drivers.transports",
        "app.drivers.transports.modbus_tcp",
    }
    for name in list(sys.modules):
        if name.startswith("app.drivers.") and name not in keep:
            del sys.modules[name]
