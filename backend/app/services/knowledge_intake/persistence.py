"""Knowledge Intake persistence facade.

Private helpers remain in service.py during the compatibility-preserving extraction.
"""

from .service import _read_json, _record_draft_sql, _record_export_sql, _record_file_sql, _record_session_sql, _update_session, _write_json

__all__ = [
    "_read_json",
    "_write_json",
    "_update_session",
    "_record_session_sql",
    "_record_file_sql",
    "_record_draft_sql",
    "_record_export_sql",
]
