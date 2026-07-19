"""Knowledge Intake package-building facade.

Private implementation helpers are re-exported only for incremental refactor/test compatibility.
"""

from .service import _build_package_zip, _try_materialize_uploaded_package_tables

__all__ = ["_build_package_zip", "_try_materialize_uploaded_package_tables"]
