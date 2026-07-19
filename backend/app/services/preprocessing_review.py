"""Compatibility alias for preprocessing review.

New code should import from backend.app.services.data_preprocessing.review.
"""

from __future__ import annotations

import sys

from .data_preprocessing import review as _module

sys.modules[__name__] = _module
