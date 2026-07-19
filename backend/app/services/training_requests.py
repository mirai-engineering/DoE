"""Compatibility alias for training requests.

New code should import from backend.app.services.ml_preprocessing_harness.training_requests.
"""

from __future__ import annotations

import sys

from .ml_preprocessing_harness import training_requests as _module

sys.modules[__name__] = _module
