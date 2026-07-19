"""Compatibility alias for moved service module.

New code should import from the new package path. This aliases the module
object so legacy monkeypatches mutate live implementation globals.
"""

from __future__ import annotations

import sys

from .model_serving import registry as _module

sys.modules[__name__] = _module
