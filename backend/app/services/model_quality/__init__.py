"""Model Quality service package.

The package proxies unknown attribute access and mutation to ``service`` so legacy
``from app.services import model_quality`` monkeypatches still affect live
implementation globals, while ``model_quality.service`` remains importable.
"""

from __future__ import annotations

from types import ModuleType
import sys

from . import service as _service


class _ServiceProxyModule(ModuleType):
    def __getattr__(self, name: str):
        return getattr(_service, name)

    def __setattr__(self, name: str, value):
        if name.startswith("__") or name in {"_service"}:
            return super().__setattr__(name, value)
        setattr(_service, name, value)

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(dir(_service)))


_module = sys.modules[__name__]
_module.__class__ = _ServiceProxyModule

for _name in dir(_service):
    if not _name.startswith("__") and _name not in globals():
        globals()[_name] = getattr(_service, _name)
