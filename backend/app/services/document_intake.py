"""Compatibility alias for the Knowledge Intake harness.

New code should import from backend.app.services.knowledge_intake.
"""

from __future__ import annotations

import sys

from .knowledge_intake import service as _module

sys.modules[__name__] = _module
