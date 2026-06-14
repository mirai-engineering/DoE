from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_COLUMN_FIELDS = {"table", "name", "role", "dtype", "required"}
DOCUMENTED_DICTIONARY_FIELDS = {
    "source_name",
    "variable_id",
    "ui_label",
    "role",
    "dtype",
    "unit",
    "required",
    "allowed_min",
    "allowed_max",
    "direction",
    "description",
    "join_key",
    "split_hint",
    "plot_role",
}
MODEL_ROLES = {"input", "output"}
CANONICAL_MODEL_TABLE = "model_table.csv"
FIXED_SOURCE_TABLES = {"experiments.csv", "conditions.csv", "results.csv"}
FIXED_SOURCE_REQUIRED_KEYS = {
    "experiments.csv": {"experiment_id"},
    "conditions.csv": {"condition_id", "experiment_id"},
    "results.csv": {"result_id"},
}
SUPPORTED_ROLES = {"id", "input", "output", "metadata", "context", "group", "time", "cycle", "sequence", "curve_axis", "ignore"}
SUPPORTED_DTYPES = {"float", "int", "integer", "number", "numeric", "string", "str", "category", "categorical", "bool", "boolean"}
SUPPORTED_DIRECTIONS = {"maximize", "minimize", "target"}
SUPPORTED_TEMPLATES = {"generic_tabular_doe"}
VARIABLE_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
INPUT_VARIABLE_ID_RE = re.compile(r"^x([1-9][0-9]*)$")
OUTPUT_VARIABLE_ID_RE = re.compile(r"^y([1-9][0-9]*)$")
RESERVED_MODEL_VARIABLE_ID_RE = re.compile(r"^[xy]([1-9][0-9]*)$")


@dataclass(frozen=True)
class ContractPaths:
    manifest_path: Path
    data_dictionary_path: Path | None = None


class ContractValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Mirai data contract is incomplete: " + "; ".join(errors))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_contract_files(root: Path) -> ContractPaths:
    manifest_path = root / "mirai_manifest.json"
    dictionary_path = root / "data_dictionary.csv"
    errors: list[str] = []
    if not manifest_path.exists():
        errors.append("Missing required mirai_manifest.json file")
    if not dictionary_path.exists():
        errors.append("Missing required data_dictionary.csv file")
    if errors:
        raise ContractValidationError(errors)
    return ContractPaths(manifest_path=manifest_path, data_dictionary_path=dictionary_path)


def _dictionary_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None or path.suffix.lower() != ".csv":
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _clean_optional(value: Any) -> Any:
    if value in {"", None, "null"}:
        return None
    return value


def _normalize_column(raw: dict[str, Any], dictionary_by_key: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    table = str(raw.get("table") or raw.get("path") or "").strip()
    raw_source = str(raw.get("source_name") or raw.get("column_name") or raw.get("name") or "").strip()
    raw_variable = str(raw.get("variable_id") or raw.get("name") or "").strip()
    dictionary_row = dictionary_by_key.get((table, raw_source), {}) or dictionary_by_key.get((table, raw_variable), {})
    merged: dict[str, Any] = {**dictionary_row, **raw}
    source_name = str(merged.get("source_name") or merged.get("column_name") or merged.get("name") or raw_source).strip()
    variable_id = str(merged.get("variable_id") or merged.get("name") or raw_variable).strip()
    name = variable_id or source_name
    role = str(merged.get("role") or "").strip().lower()
    dtype = str(merged.get("dtype") or merged.get("type") or "").strip().lower()
    unit = merged.get("unit")
    direction = merged.get("direction")
    normalized = {
        "table": table,
        "source_table": table,
        "source_name": source_name,
        "variable_id": variable_id,
        "name": name,
        "role": role,
        "dtype": dtype,
        "unit": _clean_optional(unit),
        "required": _bool(merged.get("required"), default=role in MODEL_ROLES),
        "allowed_min": merged.get("allowed_min", merged.get("min")),
        "allowed_max": merged.get("allowed_max", merged.get("max")),
        "direction": _clean_optional(direction),
        "ui_label": merged.get("ui_label") or merged.get("label") or name.replace("_", " ").title(),
        "description": merged.get("description") or "",
        "join_key": _clean_optional(merged.get("join_key")),
        "split_hint": _clean_optional(merged.get("split_hint")),
        "plot_role": _clean_optional(merged.get("plot_role")),
    }
    for bound in ("allowed_min", "allowed_max"):
        if normalized[bound] in {"", None, "null"}:
            normalized[bound] = None
        else:
            try:
                normalized[bound] = float(normalized[bound])
            except (TypeError, ValueError):
                pass
    return normalized


def _validate_fixed_source_model_variable_ids(columns: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    role_specs = {
        "input": ("x", INPUT_VARIABLE_ID_RE),
        "output": ("y", OUTPUT_VARIABLE_ID_RE),
    }
    for role, (prefix, pattern) in role_specs.items():
        role_columns = [column for column in columns if column.get("role") == role]
        ordinals: list[int] = []
        for column in role_columns:
            variable_id = str(column.get("variable_id") or "")
            match = pattern.fullmatch(variable_id)
            if not match:
                errors.append(
                    f"{role.title()} column {column.get('source_name') or column.get('name')} must use contiguous generic variable_id values "
                    f"{prefix}1..{prefix}N; put domain names in ui_label/source_name, not variable_id"
                )
                continue
            ordinals.append(int(match.group(1)))
        expected = list(range(1, len(role_columns) + 1))
        if sorted(ordinals) != expected:
            errors.append(f"{role.title()} variable_id values must be contiguous {prefix}1..{prefix}N with no gaps; found {sorted(ordinals)}")
    for column in columns:
        role = column.get("role")
        variable_id = str(column.get("variable_id") or "")
        if role not in MODEL_ROLES and RESERVED_MODEL_VARIABLE_ID_RE.fullmatch(variable_id):
            errors.append(f"Non-model column {column.get('source_name') or column.get('name')} cannot use reserved model variable_id {variable_id!r}")
    return errors


def load_and_validate_contract(raw_root: Path) -> dict[str, Any]:
    paths = find_contract_files(raw_root)
    manifest = _read_json(paths.manifest_path)
    dictionary_rows = _dictionary_rows(paths.data_dictionary_path)
    dictionary_by_key = {}
    for row in dictionary_rows:
        table = str(row.get("path") or row.get("table") or "").strip()
        source_name = str(row.get("source_name") or row.get("column_name") or row.get("name") or "").strip()
        variable_id = str(row.get("variable_id") or row.get("name") or "").strip()
        for key_name in {source_name, variable_id}:
            if table and key_name:
                dictionary_by_key[(table, key_name)] = row

    errors: list[str] = []
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    template_id = str(project.get("template_id") or manifest.get("template_id") or "generic_tabular_doe")
    if template_id not in SUPPORTED_TEMPLATES:
        errors.append(f"Unsupported template_id {template_id!r}; expected one of {sorted(SUPPORTED_TEMPLATES)}")
    tables = manifest.get("tables") if isinstance(manifest.get("tables"), list) else []
    if not tables:
        errors.append("Manifest must declare at least one table")
    table_paths = {str(table.get("path") or "") for table in tables if isinstance(table, dict)}
    has_model_table = CANONICAL_MODEL_TABLE in table_paths and (raw_root / CANONICAL_MODEL_TABLE).exists()
    has_fixed_sources = FIXED_SOURCE_TABLES.issubset(table_paths) and all((raw_root / path).exists() for path in FIXED_SOURCE_TABLES)
    if not has_model_table and not has_fixed_sources:
        errors.append(
            "Mirai package must either include model_table.csv or the fixed source tables "
            "experiments.csv, conditions.csv, and results.csv"
        )
    if has_fixed_sources:
        allowed_declared_tables = set(FIXED_SOURCE_TABLES)
        if has_model_table:
            allowed_declared_tables.add(CANONICAL_MODEL_TABLE)
        extra_tables = table_paths - allowed_declared_tables
        if extra_tables:
            errors.append(f"Fixed Mirai source-table packages may only declare experiments.csv, conditions.csv, and results.csv; unexpected tables: {sorted(extra_tables)}")
        for path, required_keys in FIXED_SOURCE_REQUIRED_KEYS.items():
            table_decl = next((table for table in tables if isinstance(table, dict) and table.get("path") == path), {})
            declared_primary_key = set(table_decl.get("primary_key") or [])
            if not required_keys.issubset(declared_primary_key):
                errors.append(f"{path} primary_key must include {sorted(required_keys)}")
    columns_raw = manifest.get("columns") if isinstance(manifest.get("columns"), list) else []
    if not columns_raw:
        errors.append("Manifest must declare columns with roles/dtypes/units")
    columns = [_normalize_column(column, dictionary_by_key) for column in columns_raw if isinstance(column, dict)]
    variable_ids: list[str] = []
    for idx, column in enumerate(columns, start=1):
        missing = [field for field in REQUIRED_COLUMN_FIELDS if column.get(field) in {None, ""}]
        if missing:
            errors.append(f"Column #{idx} missing required fields: {missing}")
        if has_fixed_sources:
            if column.get("variable_id") in {None, ""}:
                errors.append(f"Column #{idx} in fixed source package is missing required variable_id")
            if column.get("source_name") in {None, ""}:
                errors.append(f"Column #{idx} in fixed source package is missing required source_name")
        if column.get("variable_id"):
            variable_ids.append(str(column["variable_id"]))
            if not VARIABLE_ID_RE.fullmatch(str(column["variable_id"])):
                errors.append(f"Column {column.get('source_name') or column.get('name')} has unsafe variable_id {column.get('variable_id')!r}; use letters, numbers, and underscores, starting with a letter or underscore")
        if column.get("table") not in table_paths:
            errors.append(f"Column {column.get('name')} references undeclared table {column.get('table')}")
        if column.get("role") not in SUPPORTED_ROLES:
            errors.append(f"Column {column.get('name')} has unsupported role {column.get('role')!r}")
        if column.get("dtype") not in SUPPORTED_DTYPES:
            errors.append(f"Column {column.get('name')} has unsupported dtype {column.get('dtype')!r}")
        if column.get("role") == "input" and not column.get("unit"):
            errors.append(f"Input column {column.get('name')} must declare a unit; use 'unitless' if dimensionless")
        if column.get("role") == "output":
            if not column.get("unit"):
                errors.append(f"Output column {column.get('name')} must declare a unit; use 'unitless' if dimensionless")
            if column.get("direction") not in SUPPORTED_DIRECTIONS:
                errors.append(f"Output column {column.get('name')} must declare direction maximize|minimize|target")
    duplicate_variable_ids = sorted({variable_id for variable_id in variable_ids if variable_ids.count(variable_id) > 1})
    if duplicate_variable_ids:
        errors.append(f"variable_id values must be unique across generated model columns; duplicates: {duplicate_variable_ids}")
    if has_fixed_sources:
        errors.extend(_validate_fixed_source_model_variable_ids(columns))
        for structural_id in {"experiment_id", "condition_id", "result_id"}:
            matching = [column for column in columns if column.get("source_name") == structural_id or column.get("variable_id") == structural_id]
            if matching and any(column.get("variable_id") != structural_id for column in matching):
                errors.append(f"Fixed structural key {structural_id} must preserve variable_id={structural_id}")
    if not any(column.get("role") == "input" for column in columns):
        errors.append("At least one input column is required")
    if not any(column.get("role") == "output" for column in columns):
        errors.append("At least one output column is required")
    joins = manifest.get("joins") if isinstance(manifest.get("joins"), list) else []
    if has_fixed_sources and CANONICAL_MODEL_TABLE not in table_paths and not joins:
        joins = [
            {"left_table": "experiments.csv", "right_table": "conditions.csv", "keys": ["experiment_id"], "relationship": "one_to_many"},
            {"left_table": "conditions.csv", "right_table": "results.csv", "keys": ["condition_id"], "relationship": "one_to_one"},
        ]
    for idx, join in enumerate(joins, start=1):
        if not isinstance(join, dict):
            errors.append(f"Join #{idx} must be an object")
            continue
        if join.get("left_table") not in table_paths or join.get("right_table") not in table_paths:
            errors.append(f"Join #{idx} references undeclared table")
        if not join.get("keys"):
            errors.append(f"Join #{idx} must declare keys")
        if join.get("relationship") not in {"one_to_one", "one_to_many", "many_to_one"}:
            errors.append(f"Join #{idx} relationship must be one_to_one|one_to_many|many_to_one")
    if errors:
        raise ContractValidationError(errors)
    return {
        **manifest,
        "manifest_version": str(manifest.get("manifest_version") or "0.2"),
        "project": {**project, "template_id": template_id},
        "columns": columns,
        "joins": joins,
        "contract_files": {"manifest": str(paths.manifest_path), "data_dictionary": str(paths.data_dictionary_path) if paths.data_dictionary_path else None},
    }


def schema_from_contract(contract: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project = contract.get("project", {})
    inputs = []
    outputs = []
    metadata_vars = []
    for column in contract.get("columns", []):
        item = {
            "name": column["variable_id"] or column["name"],
            "variable_id": column["variable_id"] or column["name"],
            "label": column.get("ui_label") or column["name"],
            "ui_label": column.get("ui_label") or column["name"],
            "type": "continuous" if column.get("dtype") in {"float", "int", "integer", "number", "numeric"} else "categorical",
            "dtype": column.get("dtype"),
            "unit": column.get("unit") or "",
            "role": column.get("role"),
            "source_table": column.get("source_table") or column.get("table"),
            "source_name": column.get("source_name") or column.get("name"),
            "description": column.get("description") or "",
        }
        if column.get("allowed_min") is not None:
            item["min"] = column.get("allowed_min")
        if column.get("allowed_max") is not None:
            item["max"] = column.get("allowed_max")
        if column.get("role") == "input":
            inputs.append(item)
        elif column.get("role") == "output":
            outputs.append({**item, "direction": column.get("direction")})
        elif column.get("role") != "ignore":
            metadata_vars.append(item)
    return {
        "project_id": project_id or project.get("project_id") or "uploaded_project",
        "display_name": project.get("display_name") or project_id or "Uploaded Project",
        "description": project.get("description") or "Mirai contract-driven uploaded project.",
        "schema_version": "mirai-contract-0.2",
        "allow_unknown_inputs": False,
        "inputs": inputs,
        "outputs": outputs,
        "metadata": {
            "domain": project.get("domain") or "generic_tabular_doe",
            "template_id": project.get("template_id") or "generic_tabular_doe",
            "variables": metadata_vars,
            "split_hints": contract.get("split_hints", {}),
            "joins": contract.get("joins", []),
            "dictionary_fields": sorted(DOCUMENTED_DICTIONARY_FIELDS),
            "all_variables": [
                {
                    "name": column.get("variable_id") or column.get("name"),
                    "variable_id": column.get("variable_id") or column.get("name"),
                    "label": column.get("ui_label") or column.get("name"),
                    "ui_label": column.get("ui_label") or column.get("name"),
                    "role": column.get("role"),
                    "source_table": column.get("source_table") or column.get("table"),
                    "source_name": column.get("source_name") or column.get("name"),
                    "description": column.get("description") or "",
                    "unit": column.get("unit") or "",
                    "dtype": column.get("dtype"),
                }
                for column in contract.get("columns", [])
                if column.get("role") != "ignore"
            ],
        },
    }
