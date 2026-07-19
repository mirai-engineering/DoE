"""Compatibility alias for Design Studio business impact summaries."""

from __future__ import annotations

import sys

from .design_studio import business_impact as _module

sys.modules[__name__] = _module
