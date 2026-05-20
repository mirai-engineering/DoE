from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_COLUMN_FIELDS = {"table", "name", "role", "dtype", "required"}
MODEL_ROLES = {"input", "output"}
SUPPORTED_ROLES = {"id", "input", "output", "metadata", "context", "group", "time", "cycle", "sequence", "curve_axis", "ignore"}
SUPPORTED_DTYPES = {"float", "int", "integer", "number", "numeric", "string", "str", "category", "categorical", "bool", "boolean"}
SUPPORTED_DIRECTIONS = {"maximize", "minimize", "target"}
SUPPORTED_TEMPLATES = {"fuel_cell", "generic_tabular_doe"}


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
    manifests = sorted([p for p in root.iterdir() if p.is_file() and "manifest" in p.name.lower() and p.suffix.lower() in {".json", ".yml", ".yaml"}])
    dictionaries = sorted([p for p in root.iterdir() if p.is_file() and "data_dictionary" in p.name.lower() and p.suffix.lower() in {".csv", ".xlsx", ".xls"}])
    if not manifests:
        raise ContractValidationError(["Missing required Mirai manifest JSON/YAML file"])
    if not dictionaries:
        raise ContractValidationError(["Missing required data_dictionary CSV/XLSX file"])
    if manifests[0].suffix.lower() != ".json":
        raise ContractValidationError(["MVP contract parser currently requires JSON manifest files"])
    return ContractPaths(manifest_path=manifests[0], data_dictionary_path=dictionaries[0])


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


def _normalize_column(raw: dict[str, Any], dictionary_by_key: dict[tuple[str, str], dict[str, str]]) -> dict[str, Any]:
    table = str(raw.get("table") or raw.get("path") or "").strip()
    name = str(raw.get("name") or raw.get("column_name") or "").strip()
    merged: dict[str, Any] = {**dictionary_by_key.get((table, name), {}), **raw}
    role = str(merged.get("role") or "").strip().lower()
    dtype = str(merged.get("dtype") or merged.get("type") or "").strip().lower()
    unit = merged.get("unit")
    direction = merged.get("direction")
    normalized = {
        "table": table,
        "name": name,
        "role": role,
        "dtype": dtype,
        "unit": None if unit in {"", "null"} else unit,
        "required": _bool(merged.get("required"), default=role in MODEL_ROLES),
        "allowed_min": merged.get("allowed_min", merged.get("min")),
        "allowed_max": merged.get("allowed_max", merged.get("max")),
        "direction": None if direction in {"", "null"} else direction,
        "ui_label": merged.get("ui_label") or merged.get("label") or name.replace("_", " ").title(),
        "description": merged.get("description") or "",
        "join_key": merged.get("join_key") or None,
        "split_hint": merged.get("split_hint") or None,
        "plot_role": merged.get("plot_role") or None,
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


def load_and_validate_contract(raw_root: Path) -> dict[str, Any]:
    paths = find_contract_files(raw_root)
    manifest = _read_json(paths.manifest_path)
    dictionary_rows = _dictionary_rows(paths.data_dictionary_path)
    dictionary_by_key = {}
    for row in dictionary_rows:
        table = str(row.get("path") or row.get("table") or "").strip()
        name = str(row.get("column_name") or row.get("name") or "").strip()
        if table and name:
            dictionary_by_key[(table, name)] = row

    errors: list[str] = []
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    template_id = str(project.get("template_id") or manifest.get("template_id") or "generic_tabular_doe")
    if template_id not in SUPPORTED_TEMPLATES:
        errors.append(f"Unsupported template_id {template_id!r}; expected one of {sorted(SUPPORTED_TEMPLATES)}")
    tables = manifest.get("tables") if isinstance(manifest.get("tables"), list) else []
    if not tables:
        errors.append("Manifest must declare at least one table")
    table_paths = {str(table.get("path") or "") for table in tables if isinstance(table, dict)}
    columns_raw = manifest.get("columns") if isinstance(manifest.get("columns"), list) else []
    if not columns_raw:
        errors.append("Manifest must declare columns with roles/dtypes/units")
    columns = [_normalize_column(column, dictionary_by_key) for column in columns_raw if isinstance(column, dict)]
    for idx, column in enumerate(columns, start=1):
        missing = [field for field in REQUIRED_COLUMN_FIELDS if column.get(field) in {None, ""}]
        if missing:
            errors.append(f"Column #{idx} missing required fields: {missing}")
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
    if not any(column.get("role") == "input" for column in columns):
        errors.append("At least one input column is required")
    if not any(column.get("role") == "output" for column in columns):
        errors.append("At least one output column is required")
    joins = manifest.get("joins") if isinstance(manifest.get("joins"), list) else []
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
            "name": column["name"],
            "label": column.get("ui_label") or column["name"],
            "type": "continuous" if column.get("dtype") in {"float", "int", "integer", "number", "numeric"} else "categorical",
            "unit": column.get("unit") or "",
            "role": column.get("role"),
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
        },
    }
