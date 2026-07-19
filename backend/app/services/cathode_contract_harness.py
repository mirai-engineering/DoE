"""Compatibility alias for the Knowledge Intake Fraunhofer demo adapter."""

from __future__ import annotations

import sys

from .knowledge_intake import demo_adapters as _module

sys.modules[__name__] = _module
