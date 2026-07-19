"""Compatibility alias for ML preprocessing.

New code should import from backend.app.services.ml_preprocessing_harness.lifecycle.
This aliases the module object so legacy private imports and monkeypatches keep
working against the live implementation globals.
"""

from __future__ import annotations

import sys

from .ml_preprocessing_harness import lifecycle as _module

sys.modules[__name__] = _module
