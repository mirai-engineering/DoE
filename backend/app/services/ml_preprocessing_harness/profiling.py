"""ML preprocessing profiling facade."""

from .lifecycle import get_column_profile, get_missingness_report

__all__ = ["get_column_profile", "get_missingness_report"]
