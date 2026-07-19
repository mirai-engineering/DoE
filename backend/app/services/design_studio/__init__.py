"""Design Studio tab service package.

The package proxies unknown attribute access and mutation to ``service`` so legacy
``from app.services import design_studio`` monkeypatches still affect live
implementation globals, while submodules such as ``design_studio.business_impact``
remain importable.
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

# Populate common public attributes for star imports/introspection; mutation still
# forwards through _ServiceProxyModule.__setattr__ when callers monkeypatch the package.
for _name in dir(_service):
    if not _name.startswith("__") and _name not in globals():
        globals()[_name] = getattr(_service, _name)
