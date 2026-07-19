"""Knowledge Intake session facade.

Implementation currently lives in service.py to preserve behavior during the structural refactor.
"""

from .service import create_document_intake_session, get_document_intake_session, list_document_intake_sessions

__all__ = ["create_document_intake_session", "get_document_intake_session", "list_document_intake_sessions"]
