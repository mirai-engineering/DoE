"""Compatibility alias for Data Intake ingestion sessions.

New code should import from backend.app.services.data_preprocessing.ingestion_sessions.
This module aliases the new module object so legacy monkeypatches against
app.services.data_intake still mutate the live implementation globals.
"""

from __future__ import annotations

import sys

from .data_preprocessing import ingestion_sessions as _module

sys.modules[__name__] = _module
