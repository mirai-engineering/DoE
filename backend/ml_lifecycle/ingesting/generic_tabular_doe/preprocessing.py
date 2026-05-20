from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer

from .contract import ContractValidationError, load_and_validate_contract, schema_from_contract
from ml_lifecycle.ingesting.extractors.pem_cell_zip_bundle import run_pem_cell_zip_bundle


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def _read_table(raw_root: Path, relative_path: str, generated_tables: dict[str, Path] | None = None) -> pd.DataFrame:
    path = generated_tables.get(relative_path) if generated_tables and relative_path in generated_tables else raw_root / relative_path
    if not path.exists():
        raise ContractValidationError([f"Declared table file is missing: {relative_path}"])
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ContractValidationError([f"Unsupported table file type for {relative_path}; MVP supports CSV and XLSX"])


def _coerce_column(series: pd.Series, dtype: str) -> pd.Series:
    if dtype in {"float", "number", "numeric"}:
        return pd.to_numeric(series, errors="coerce").astype("float64")
    if dtype in {"int", "integer"}:
        return pd.to_numeric(series, errors="coerce")
    if dtype in {"bool", "boolean"}:
        return series.map(lambda v: np.nan if pd.isna(v) else str(v).strip().lower() in {"1", "true", "yes", "y"})
    return series.astype("string")


def _build_joined_table(raw_root: Path, contract: dict[str, Any], generated_tables: dict[str, Path] | None = None) -> pd.DataFrame:
    tables = {str(table["path"]): _read_table(raw_root, str(table["path"]), generated_tables=generated_tables) for table in contract.get("tables", [])}
    if not contract.get("joins"):
        if len(tables) != 1:
            raise ContractValidationError(["Multi-table contracts must declare joins. For MVP use one model_table.csv or explicit one_to_one/one_to_many joins."])
        return next(iter(tables.values())).copy()
    base_path = str(contract["joins"][0]["left_table"])
    frame = tables[base_path].copy()
    joined = {base_path}
    for join in contract.get("joins", []):
        left = str(join["left_table"])
        right = str(join["right_table"])
        keys = list(join.get("keys") or [])
        if left not in joined:
            raise ContractValidationError([f"Unsupported join order: {left} must already be joined before joining {right}. Declare joins from metadata/sample table outward."])
        relationship = join.get("relationship")
        validate = "one_to_one" if relationship == "one_to_one" else "one_to_many"
        try:
            frame = frame.merge(tables[right], on=keys, how="inner", validate=validate, suffixes=("", f"__{Path(right).stem}"))
        except Exception as exc:  # noqa: BLE001
            raise ContractValidationError([f"Join {left} -> {right} on {keys} failed: {exc}"]) from exc
        joined.add(right)
    return frame


def _is_metadata_zip_member(name: str) -> bool:
    parts = Path(name).parts
    return not parts or parts[0] == "__MACOSX" or any(part == ".DS_Store" for part in parts) or Path(name).name.startswith("._")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_archive_globs(raw_reference: dict[str, Any]) -> list[str]:
    value = raw_reference.get("archive_globs") or raw_reference.get("zip_globs") or raw_reference.get("cell_archives_glob")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _process_raw_reference_zips(raw_root: Path, artifact_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    raw_reference = contract.get("raw_reference_files") if isinstance(contract.get("raw_reference_files"), dict) else {}
    archive_globs = _normalize_archive_globs(raw_reference)
    if not archive_globs:
        return {"enabled": False, "reason": "No raw_reference_files.cell_archives_glob/archive_globs declared"}

    archive_paths: list[Path] = []
    for pattern in archive_globs:
        archive_paths.extend(sorted(raw_root.glob(pattern)))
        if "/" in pattern or "\\" in pattern:
            archive_paths.extend(sorted(raw_root.glob(Path(pattern).name)))
    unique_archives = sorted({path.resolve(): path for path in archive_paths if path.is_file() and path.suffix.lower() == ".zip"}.values())

    # Important: raw/reference archives are audit inputs, not model-table artifacts.
    # Do not extract them into training artifacts. A previous implementation expanded
    # every Cell_NN.zip into raw_reference_extracted/, creating 10k+ CSV files during
    # preprocessing/training activation. Keep only a bounded in-ZIP inventory.
    max_member_preview = int(raw_reference.get("max_member_preview", 200) or 200)
    archives: list[dict[str, Any]] = []
    errors: list[str] = []
    cell_re = re.compile(r"^Cell_(\d{2})\.zip$", re.IGNORECASE)
    for archive_path in unique_archives:
        match = cell_re.fullmatch(archive_path.name)
        archive_id = f"Cell_{match.group(1)}" if match else archive_path.stem
        member_preview: list[dict[str, Any]] = []
        member_count = 0
        csv_member_count = 0
        skipped_member_count = 0
        total_uncompressed_bytes = 0
        try:
            with ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    name = member.filename.replace("\\", "/")
                    if member.is_dir() or _is_metadata_zip_member(name):
                        skipped_member_count += 1
                        continue
                    member_count += 1
                    total_uncompressed_bytes += int(member.file_size)
                    if name.lower().endswith(".csv"):
                        csv_member_count += 1
                    if len(member_preview) < max_member_preview:
                        member_preview.append(
                            {
                                "archive_member": name,
                                "size_bytes": int(member.file_size),
                                "compressed_size_bytes": int(member.compress_size),
                                "crc": int(member.CRC),
                                "is_csv": name.lower().endswith(".csv"),
                            }
                        )
        except BadZipFile:
            errors.append(f"Invalid zip archive: {archive_path.relative_to(raw_root)}")
            continue
        archives.append(
            {
                "archive": str(archive_path.relative_to(raw_root)),
                "archive_id": archive_id,
                "size_bytes": archive_path.stat().st_size,
                "sha256": _sha256(archive_path),
                "member_count": member_count,
                "csv_member_count": csv_member_count,
                "total_uncompressed_bytes": total_uncompressed_bytes,
                "member_preview_count": len(member_preview),
                "members_preview": member_preview,
                "skipped_member_count": skipped_member_count,
            }
        )
    return {
        "enabled": True,
        "archive_globs": archive_globs,
        "archive_count": len(archives),
        "extracted_root": None,
        "archives": archives,
        "errors": errors,
        "note": "Raw reference ZIPs are inventoried in place without extraction. Generic training consumes only declared CSV/XLSX model tables.",
    }



def _run_raw_extractors(raw_root: Path, canonical_dir: Path, artifact_dir: Path, contract: dict[str, Any]) -> tuple[dict[str, Path], dict[str, Any]]:
    extractors = contract.get("raw_extractors") if isinstance(contract.get("raw_extractors"), list) else []
    if not extractors:
        return {}, {"enabled": False, "reason": "No raw_extractors declared"}
    generated_tables: dict[str, Path] = {}
    reports: list[dict[str, Any]] = []
    for index, extractor in enumerate(extractors, start=1):
        if not isinstance(extractor, dict):
            raise ContractValidationError([f"raw_extractors[{index}] must be an object"])
        kind = str(extractor.get("kind") or "")
        if kind != "pem_cell_zip_bundle":
            raise ContractValidationError([f"Unsupported raw extractor kind {kind!r}; supported: pem_cell_zip_bundle"])
        output_table, generated_table_path, report = run_pem_cell_zip_bundle(raw_root=raw_root, canonical_dir=canonical_dir, artifact_dir=artifact_dir, extractor=extractor, index=index)
        generated_tables[output_table] = generated_table_path
        reports.append(report)
    return generated_tables, {"enabled": True, "extractor_count": len(reports), "extractors": reports}


def _assign_metadata_aware_grouped_splits(frame: pd.DataFrame, group_key: str) -> tuple[pd.Series, dict[str, Any]]:
    """PEM-style grouped train/validation/test split without BO holdout.

    This keeps full cells together while spreading validation/test cells across the
    observed formulation/degradation metadata range. BO should reuse train+validation
    later rather than reserving a separate BO holdout in sparse DoE datasets.
    """
    metadata_columns = [column for column in ["pt_c_ratio", "i_c_ratio", "ionomer_ew", "ast_rh", "ast_upl"] if column in frame.columns]
    split = pd.Series("train", index=frame.index, dtype="object")
    groups = sorted(frame[group_key].dropna().astype(str).unique())
    if len(groups) < 3:
        return split, {"strategy": "metadata_aware_grouped_by_cell_id", "group_key": group_key, "split_cell_ids": {"train": groups, "validation": [], "test": []}, "split_counts": split.value_counts().to_dict()}
    if metadata_columns:
        group_features = frame.groupby(group_key)[metadata_columns].first().apply(pd.to_numeric, errors="coerce").sort_index()
        normalized = (group_features - group_features.min()) / (group_features.max() - group_features.min()).replace(0, 1)
        ordered_groups = list(normalized.fillna(0.5).mean(axis=1).sort_values().index.astype(str))
    else:
        ordered_groups = groups
    n_test = max(1, round(len(ordered_groups) * 0.15))
    n_val = max(1, round(len(ordered_groups) * 0.15))
    test_groups = ordered_groups[:: max(1, len(ordered_groups) // n_test)][:n_test]
    remaining = [group for group in ordered_groups if group not in test_groups]
    validation_groups = remaining[:: max(1, len(remaining) // n_val)][:n_val]
    train_groups = [group for group in remaining if group not in validation_groups]
    values = frame[group_key].astype(str)
    split.loc[values.isin(test_groups)] = "test"
    split.loc[values.isin(validation_groups)] = "validation"
    return split, {
        "strategy": "metadata_aware_grouped_by_cell_id",
        "group_key": group_key,
        "metadata_score_columns": metadata_columns,
        "split_cell_ids": {"train": train_groups, "validation": validation_groups, "test": test_groups},
        "split_counts": split.value_counts().to_dict(),
        "bo_holdout_policy": "not_reserved; BO uses train+validation and keeps test untouched",
    }


def _assign_splits(frame: pd.DataFrame, split_hints: dict[str, Any]) -> tuple[pd.Series, dict[str, Any]]:
    predefined = split_hints.get("predefined_split_column")
    if predefined and predefined in frame.columns:
        split = frame[predefined].astype(str).str.lower().replace({"val": "validation", "valid": "validation"})
        return split, {"strategy": "predefined_column", "split_column": predefined, "split_counts": split.value_counts().to_dict()}
    group_key = split_hints.get("group_key")
    strategy = split_hints.get("recommended_strategy") or ("grouped" if group_key else "random")
    validation_fraction = float(split_hints.get("validation_fraction") or 0.15)
    holdout_fraction = float(split_hints.get("holdout_fraction") or 0.15)
    rng = np.random.default_rng(13)
    split = pd.Series("train", index=frame.index, dtype="object")
    if strategy in {"metadata_aware_grouped", "metadata_aware_grouped_by_cell_id", "pem_metadata_aware_grouped"} and group_key and group_key in frame.columns:
        return _assign_metadata_aware_grouped_splits(frame, group_key)
    if strategy == "grouped" and group_key and group_key in frame.columns:
        groups = np.array(sorted(frame[group_key].dropna().astype(str).unique()))
        rng.shuffle(groups)
        n_test = max(1, int(round(len(groups) * holdout_fraction))) if len(groups) >= 3 else 0
        n_val = max(1, int(round(len(groups) * validation_fraction))) if len(groups) >= 3 else 0
        test_groups = set(groups[:n_test])
        val_groups = set(groups[n_test:n_test + n_val])
        values = frame[group_key].astype(str)
        split.loc[values.isin(test_groups)] = "test"
        split.loc[values.isin(val_groups)] = "validation"
        return split, {"strategy": "grouped", "group_key": group_key, "validation_groups": sorted(val_groups), "test_groups": sorted(test_groups), "split_counts": split.value_counts().to_dict()}
    indices = np.array(frame.index)
    rng.shuffle(indices)
    n_test = max(1, int(round(len(indices) * holdout_fraction))) if len(indices) >= 5 else 0
    n_val = max(1, int(round(len(indices) * validation_fraction))) if len(indices) >= 5 else 0
    split.loc[indices[:n_test]] = "test"
    split.loc[indices[n_test:n_test + n_val]] = "validation"
    return split, {"strategy": "random", "seed": 13, "split_counts": split.value_counts().to_dict()}


def _profile(frame: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"row_count": int(len(frame)), "column_count": int(len(frame.columns)), "columns": list(map(str, frame.columns)), "numeric_summary": {}, "missing_by_column": {str(k): int(v) for k, v in frame.isna().sum().to_dict().items()}}
    numeric = frame[[c for c in columns if c in frame.columns]].select_dtypes(include="number")
    if not numeric.empty:
        result["numeric_summary"] = json.loads(numeric.describe().where(pd.notnull(numeric.describe()), None).to_json())
    return result


def build_generic_preprocessing_artifacts(*, raw_root: Path, canonical_dir: Path, artifact_dir: Path, project_id: str) -> dict[str, Any]:
    contract = load_and_validate_contract(raw_root)
    schema = schema_from_contract(contract, project_id=project_id)
    generated_tables, raw_extractor_report = _run_raw_extractors(raw_root, canonical_dir, artifact_dir, contract)
    raw_reference_inventory = _process_raw_reference_zips(raw_root, artifact_dir, contract)
    columns = [column for column in contract.get("columns", []) if column.get("role") != "ignore"]
    required_columns = [column for column in columns if column.get("required")]
    inputs = [column["name"] for column in columns if column.get("role") == "input"]
    outputs = [column["name"] for column in columns if column.get("role") == "output"]
    model_columns = [column["name"] for column in columns]

    frame = _build_joined_table(raw_root, contract, generated_tables=generated_tables)
    if "row_id" not in frame.columns and any(column.get("name") == "row_id" and column.get("role") == "id" for column in columns):
        frame.insert(0, "row_id", [f"{project_id}_row_{idx + 1:05d}" for idx in range(len(frame))])
    validation_errors: list[str] = []
    for column in required_columns:
        if column["name"] not in frame.columns:
            validation_errors.append(f"Missing required column {column['name']} from table {column['table']}")
    if validation_errors:
        raise ContractValidationError(validation_errors)

    working = frame[[name for name in model_columns if name in frame.columns]].copy()
    rejected_reasons: list[dict[str, Any]] = []
    for column in columns:
        name = column["name"]
        if name not in working.columns:
            continue
        working[name] = _coerce_column(working[name], str(column.get("dtype")))
        if column.get("required"):
            mask = working[name].isna()
            for idx in working.index[mask].tolist():
                rejected_reasons.append({"row_index": int(idx), "column": name, "reason": "missing_required_value"})
        if column.get("role") in {"input", "output"}:
            numeric = pd.to_numeric(working[name], errors="coerce")
            if column.get("allowed_min") is not None:
                for idx in working.index[numeric < float(column["allowed_min"])].tolist():
                    rejected_reasons.append({"row_index": int(idx), "column": name, "reason": "below_allowed_min"})
            if column.get("allowed_max") is not None:
                for idx in working.index[numeric > float(column["allowed_max"])].tolist():
                    rejected_reasons.append({"row_index": int(idx), "column": name, "reason": "above_allowed_max"})
    rejected_index = {item["row_index"] for item in rejected_reasons}
    accepted = working.loc[[idx for idx in working.index if idx not in rejected_index]].copy()
    if accepted.empty:
        raise ContractValidationError(["No rows remain after required-value/bounds validation"])
    split_hints = dict(contract.get("split_hints") or {})
    if any((extractor.get("kind") == "pem_cell_zip_bundle") for extractor in contract.get("raw_extractors", []) if isinstance(extractor, dict)) and split_hints.get("group_key") == "cell_id" and not split_hints.get("predefined_split_column"):
        split_hints["recommended_strategy"] = split_hints.get("recommended_strategy") if split_hints.get("recommended_strategy") not in {None, "grouped"} else "metadata_aware_grouped_by_cell_id"
    accepted["split"], split_details = _assign_splits(accepted, split_hints)

    canonical_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    accepted.to_csv(canonical_dir / "model_table.csv", index=False)
    rejected_frame = pd.DataFrame(rejected_reasons, columns=["row_index", "column", "reason"])
    rejected_frame.to_csv(canonical_dir / "rejected_rows.csv", index=False)

    train = accepted[accepted["split"] == "train"]
    input_imputer = SimpleImputer(strategy="median")
    output_imputer = SimpleImputer(strategy="median")
    x_train = train[inputs].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
    y_train = train[outputs].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
    x_imp = input_imputer.fit_transform(x_train).astype(np.float32)
    y_imp = output_imputer.fit_transform(y_train).astype(np.float32)
    input_min = x_imp.min(axis=0).astype(float).tolist()
    input_max = x_imp.max(axis=0).astype(float).tolist()
    output_min = y_imp.min(axis=0).astype(float).tolist()
    output_max = y_imp.max(axis=0).astype(float).tolist()
    preprocessing = {
        "version": "mirai-generic-0.1",
        "project_id": project_id,
        "template_id": contract.get("project", {}).get("template_id"),
        "input_order": inputs,
        "output_order": outputs,
        "input_imputer": {"method": "median", "statistics": input_imputer.statistics_.astype(float).tolist()},
        "output_imputer": {"method": "median", "statistics": output_imputer.statistics_.astype(float).tolist(), "training_only": True},
        "input_scaler": {"method": "minmax", "fit_scope": "train_split_only", "min": input_min, "max": input_max},
        "output_scaler": {"method": "minmax", "fit_scope": "train_split_only", "min": output_min, "max": output_max, "clip": True},
        "split_column": "split",
    }
    validation_report = {"status": "passed", "generated_at": _now(), "rejected_row_count": int(len(rejected_frame)), "errors": [], "contract_template_id": contract.get("project", {}).get("template_id")}
    dataset_profile = _profile(accepted, [*inputs, *outputs])
    split_report = {**split_details, "split_counts": {str(k): int(v) for k, v in accepted["split"].value_counts().to_dict().items()}}
    eda_report = {"generated_at": _now(), "input_distributions": dataset_profile.get("numeric_summary", {}), "missingness": dataset_profile.get("missing_by_column", {}), "rejected_rows": {"count": int(len(rejected_frame))}, "split_counts": split_report["split_counts"]}

    _write_json(artifact_dir / "schema.json", schema)
    _write_json(artifact_dir / "preprocessing.json", preprocessing)
    _write_json(artifact_dir / "split_report.json", split_report)
    _write_json(artifact_dir / "validation_report.json", validation_report)
    _write_json(artifact_dir / "dataset_profile.json", dataset_profile)
    _write_json(artifact_dir / "eda_report.json", eda_report)
    _write_json(artifact_dir / "raw_reference_inventory.json", raw_reference_inventory)
    _write_json(artifact_dir / "raw_extractor_report.json", raw_extractor_report)
    _write_json(canonical_dir / "dataset_profile.json", dataset_profile)
    _write_json(canonical_dir / "validation_report.json", validation_report)
    _write_json(canonical_dir / "raw_reference_inventory.json", raw_reference_inventory)
    _write_json(canonical_dir / "raw_extractor_report.json", raw_extractor_report)
    return {
        "project_id": project_id,
        "template_id": contract.get("project", {}).get("template_id"),
        "row_count": int(len(accepted)),
        "rejected_row_count": int(len(rejected_frame)),
        "artifact_dir": str(artifact_dir),
        "schema_path": str(artifact_dir / "schema.json"),
        "preprocessing_path": str(artifact_dir / "preprocessing.json"),
        "split_report_path": str(artifact_dir / "split_report.json"),
        "dataset_profile_path": str(artifact_dir / "dataset_profile.json"),
        "validation_report_path": str(artifact_dir / "validation_report.json"),
        "raw_reference_inventory_path": str(artifact_dir / "raw_reference_inventory.json"),
        "raw_extractor_report_path": str(artifact_dir / "raw_extractor_report.json"),
        "preprocessing_report_path": str(artifact_dir / "validation_report.json"),
    }
