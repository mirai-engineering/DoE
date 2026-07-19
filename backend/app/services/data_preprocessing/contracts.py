"""Thin access point for generic Mirai package contracts.

The source of truth remains backend/ml_lifecycle/ingesting/generic_tabular_doe.
"""

from ml_lifecycle.ingesting.generic_tabular_doe.contract import ContractValidationError, load_and_validate_contract, schema_from_contract
from ml_lifecycle.ingesting.generic_tabular_doe.preprocessing import _prepare_package_root, build_generic_preprocessing_artifacts

__all__ = [
    "ContractValidationError",
    "load_and_validate_contract",
    "schema_from_contract",
    "_prepare_package_root",
    "build_generic_preprocessing_artifacts",
]
