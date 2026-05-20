from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ml_lifecycle.ingesting.fuel_cell_doe_demo.schema import (  # noqa: E402
    ARTIFACT_DIR,
    MODEL_COLUMNS,
    OUTPUT_DIR,
    PAPER_INPUT_COLUMNS,
    PAPER_OUTPUT_COLUMNS,
    PHASE_SCOPE,
    PROJECT_ID,
    REAL_PROJECT_SCHEMA,
    TRAINING_ARTIFACT_DIR,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _scale_minmax(values: np.ndarray, minimum: np.ndarray, maximum: np.ndarray) -> np.ndarray:
    scale = np.where(maximum > minimum, maximum - minimum, 1.0)
    return ((values - minimum) / scale).astype(np.float32)


def _assign_grouped_cell_splits(frame: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    cell_features = (
        frame.groupby("cell_id")[["pt_c_ratio", "i_c_ratio", "ionomer_ew", "ast_rh", "ast_upl"]]
        .first()
        .apply(pd.to_numeric, errors="coerce")
        .sort_index()
    )
    normalized = (cell_features - cell_features.min()) / (cell_features.max() - cell_features.min()).replace(0, 1)
    score = normalized.fillna(0.5).mean(axis=1).sort_values()
    cells = list(score.index)
    if len(cells) < 8:
        split_map = {cell: "train" for cell in cells}
        return frame["cell_id"].map(split_map).fillna("train"), {"split_cell_ids": {"train": cells}, "strategy": "fallback_too_few_cells"}

    n_test = max(1, round(len(cells) * 0.15))
    n_val = max(1, round(len(cells) * 0.15))
    test_cells = cells[:: max(1, len(cells) // n_test)][:n_test]
    remaining = [cell for cell in cells if cell not in test_cells]
    validation_cells = remaining[:: max(1, len(remaining) // n_val)][:n_val]
    train_cells = [cell for cell in remaining if cell not in validation_cells]
    split_map = {cell: "train" for cell in train_cells}
    split_map.update({cell: "validation" for cell in validation_cells})
    split_map.update({cell: "test" for cell in test_cells})
    details = {
        "strategy": "metadata_aware_grouped_by_cell_id",
        "metadata_score_columns": list(cell_features.columns),
        "split_cell_ids": {
            "train": train_cells,
            "validation": validation_cells,
            "test": test_cells,
        },
        "bo_holdout_policy": "not_reserved; BO uses train+validation and keeps test untouched",
    }
    return frame["cell_id"].map(split_map), details


def _assign_smoke_split(frame: pd.DataFrame) -> pd.Series:
    """Lifecycle-aware smoke split for one cell.

    Long-term standard is grouped-by-cell splitting. With Cell_01 only, we sort
    each RH block by operating voltage and emphasize later/high-voltage rows in
    validation/test reporting while keeping all splits represented.
    """
    split = pd.Series(index=frame.index, dtype="object")
    for _rh, group in frame.groupby("operating_rh", sort=True):
        ordered = group.sort_values("operating_voltage")
        n = len(ordered)
        train_end = max(1, int(round(n * 0.6)))
        val_end = max(train_end + 1, int(round(n * 0.8))) if n > 2 else n
        val_end = min(val_end, n)
        split.loc[ordered.index[:train_end]] = "train"
        split.loc[ordered.index[train_end:val_end]] = "validation"
        split.loc[ordered.index[val_end:]] = "test"
    if split.isna().any():
        split = split.fillna("train")
    return split


def _distribution(frame: pd.DataFrame, columns: list[str]) -> dict[str, dict[str, float | None]]:
    result: dict[str, dict[str, float | None]] = {}
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        result[column] = {
            "count": int(values.count()),
            "missing": int(values.isna().sum()),
            "min": None if values.dropna().empty else float(values.min()),
            "max": None if values.dropna().empty else float(values.max()),
            "mean": None if values.dropna().empty else float(values.mean()),
            "std": None if values.dropna().empty else float(values.std(ddof=0)),
        }
    return result


def _plot_distributions(frame: pd.DataFrame, columns: list[str], out_dir: Path, prefix: str) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for column in columns:
        fig, ax = plt.subplots(figsize=(5, 3))
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if not values.empty:
            ax.hist(values, bins=min(12, max(3, len(values) // 3)), color="#2f6f73", alpha=0.85)
        ax.set_title(column)
        ax.set_xlabel(column)
        ax.set_ylabel("count")
        fig.tight_layout()
        path = out_dir / f"{prefix}_{column}.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        paths.append(str(path))
    return paths


def build_preprocessing_artifacts(
    *,
    project_id: str = PROJECT_ID,
    data_dir: Path = OUTPUT_DIR,
    artifact_dir: Path = TRAINING_ARTIFACT_DIR / "latest",
) -> dict[str, Any]:
    if project_id != PROJECT_ID:
        raise ValueError(f"Unsupported real project id: {project_id}")

    model_table_path = data_dir / "model_table.csv"
    rejected_rows_path = data_dir / "rejected_rows.csv"
    if not model_table_path.exists():
        raise FileNotFoundError(f"Missing model table: {model_table_path}")

    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = artifact_dir / "plots"

    frame = pd.read_csv(model_table_path)
    missing_columns = [column for column in MODEL_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"model_table.csv is missing required columns: {missing_columns}")

    if frame["cell_id"].nunique() > 1:
        frame["split"], split_details = _assign_grouped_cell_splits(frame)
    else:
        frame["split"] = _assign_smoke_split(frame)
        split_details = {"strategy": "Cell_01 lifecycle/cycle-aware smoke split", "split_cell_ids": {"train": ["Cell_01"]}}
    split_counts = frame["split"].value_counts().to_dict()
    input_frame = frame[PAPER_INPUT_COLUMNS].apply(pd.to_numeric, errors="coerce")
    output_frame = frame[PAPER_OUTPUT_COLUMNS].apply(pd.to_numeric, errors="coerce")

    duplicate_feature_target_rows = int(frame.duplicated(subset=MODEL_COLUMNS).sum())
    duplicate_input_rows = int(frame.duplicated(subset=PAPER_INPUT_COLUMNS).sum())

    rejected_count = 0
    rejected_reasons: dict[str, int] = {}
    if rejected_rows_path.exists():
        rejected = pd.read_csv(rejected_rows_path)
        rejected_count = int(len(rejected))
        if "reason" in rejected.columns:
            rejected_reasons = {str(k): int(v) for k, v in rejected["reason"].value_counts().items()}

    train_mask = frame["split"] == "train"
    x_train_raw = input_frame.loc[train_mask].to_numpy(dtype=np.float32)
    y_train_raw = output_frame.loc[train_mask].to_numpy(dtype=np.float32)

    input_imputer = SimpleImputer(strategy="median")
    output_imputer = SimpleImputer(strategy="median")
    x_train_imputed = input_imputer.fit_transform(x_train_raw).astype(np.float32)
    y_train_imputed = output_imputer.fit_transform(y_train_raw).astype(np.float32)

    input_min = x_train_imputed.min(axis=0).astype(np.float32)
    input_max = x_train_imputed.max(axis=0).astype(np.float32)
    output_min = y_train_imputed.min(axis=0).astype(np.float32)
    output_max = y_train_imputed.max(axis=0).astype(np.float32)

    def transform_x(df: pd.DataFrame) -> np.ndarray:
        values = df[PAPER_INPUT_COLUMNS].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
        imputed = input_imputer.transform(values).astype(np.float32)
        return _scale_minmax(imputed, input_min, input_max)

    def transform_y(df: pd.DataFrame) -> np.ndarray:
        values = df[PAPER_OUTPUT_COLUMNS].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
        imputed = output_imputer.transform(values).astype(np.float32)
        return _scale_minmax(imputed, output_min, output_max)

    transformed = frame.copy()
    for split_name in ["train", "validation", "test"]:
        split_frame = frame[frame["split"] == split_name]
        if split_frame.empty:
            continue
        x_scaled = transform_x(split_frame)
        y_scaled = transform_y(split_frame)
        for index, column in enumerate(PAPER_INPUT_COLUMNS):
            transformed.loc[split_frame.index, f"scaled_{column}"] = x_scaled[:, index]
        for index, column in enumerate(PAPER_OUTPUT_COLUMNS):
            transformed.loc[split_frame.index, f"scaled_{column}"] = y_scaled[:, index]

    transformed_path = artifact_dir / "model_table_preprocessed.csv"
    transformed.to_csv(transformed_path, index=False)

    preprocessing = {
        "version": "0.2.0-smoke",
        "project_id": project_id,
        "phase_scope": PHASE_SCOPE,
        "quality_label": "smoke/demo quality only",
        "input_order": PAPER_INPUT_COLUMNS,
        "output_order": PAPER_OUTPUT_COLUMNS,
        "input_imputer": {
            "method": "median",
            "statistics": [float(x) for x in input_imputer.statistics_],
        },
        "output_imputer": {
            "method": "median",
            "statistics": [float(x) for x in output_imputer.statistics_],
            "training_only": True,
        },
        "input_scaler": {
            "method": "minmax",
            "fit_scope": "train_split_only",
            "min": [float(x) for x in input_min],
            "max": [float(x) for x in input_max],
        },
        "output_scaler": {
            "method": "minmax",
            "fit_scope": "train_split_only",
            "min": [float(x) for x in output_min],
            "max": [float(x) for x in output_max],
            "clip": True,
        },
        "split_column": "split",
        "future_split_standard": "grouped_by_cell_id when more cells are implemented",
    }
    preprocessing_path = artifact_dir / "preprocessing.json"
    _write_json(preprocessing_path, preprocessing)

    schema_path = artifact_dir / "schema.json"
    _write_json(schema_path, REAL_PROJECT_SCHEMA)

    eda_report = {
        "project_id": project_id,
        "generated_at": _utc_now(),
        "phase_scope": PHASE_SCOPE,
        "quality_label": "smoke/demo quality only",
        "source_model_table": str(model_table_path),
        "source_model_table_sha256": _file_sha256(model_table_path),
        "row_count": int(len(frame)),
        "cell_ids": sorted(str(value) for value in frame.get("cell_id", pd.Series(dtype=str)).dropna().unique()),
        "split_counts": {str(k): int(v) for k, v in split_counts.items()},
        "missingness": {
            column: int(frame[column].isna().sum()) if column in frame.columns else None
            for column in MODEL_COLUMNS
        },
        "input_distributions": _distribution(frame, PAPER_INPUT_COLUMNS),
        "output_distributions": _distribution(frame, PAPER_OUTPUT_COLUMNS),
        "duplicate_feature_target_rows": duplicate_feature_target_rows,
        "duplicate_input_rows": duplicate_input_rows,
        "rejected_rows": {"count": rejected_count, "reasons": rejected_reasons},
        "source_provenance_columns": [
            column for column in frame.columns if "source" in column or column in {"cell_id", "test_no", "phase_scope"}
        ],
        "leakage_warnings": [
            "Test cells are held out from training, validation, model selection, and BO replay.",
            "BO replay sources observations from train+validation rows only; no separate BO holdout split is reserved.",
            "Per-output acceptance thresholds are provisional/report-only in this MVP.",
            "R² can be undefined for constant outputs in small grouped splits.",
        ],
    }
    _write_json(artifact_dir / "eda_report.json", eda_report)
    dataset_profile = {
        "project_id": project_id,
        "generated_at": _utc_now(),
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": list(map(str, frame.columns)),
        "missing_by_column": {str(column): int(count) for column, count in frame.isna().sum().to_dict().items()},
        "input_distributions": eda_report["input_distributions"],
        "output_distributions": eda_report["output_distributions"],
    }
    validation_report = {
        "project_id": project_id,
        "generated_at": _utc_now(),
        "status": "passed",
        "template_id": "fuel_cell",
        "required_columns": MODEL_COLUMNS,
        "missing_required_columns": [],
        "rejected_row_count": rejected_count,
        "errors": [],
    }
    _write_json(artifact_dir / "dataset_profile.json", dataset_profile)
    _write_json(artifact_dir / "validation_report.json", validation_report)

    split_report = {
        **split_details,
        "future_standard": "grouped_by_cell_id",
        "split_counts": eda_report["split_counts"],
        "note": "Grouped by cell_id. BO uses train+validation rows for sequential replay and keeps test cells untouched for model-quality evaluation.",
    }
    _write_json(artifact_dir / "split_report.json", split_report)

    plot_paths = _plot_distributions(frame, PAPER_OUTPUT_COLUMNS, plots_dir, "output")
    preprocessing_report = {
        "project_id": project_id,
        "generated_at": _utc_now(),
        "phase_scope": PHASE_SCOPE,
        "quality_label": "smoke/demo quality only",
        "input_imputation": preprocessing["input_imputer"],
        "output_imputation_training_only": preprocessing["output_imputer"],
        "input_scaling": preprocessing["input_scaler"],
        "output_scaling": preprocessing["output_scaler"],
        "transformed_dataset": str(transformed_path),
        "plots": plot_paths,
        "review_status": "pending_scientist_review",
        "ai_preprocessing_assistant": {
            "status": "placeholder_not_active",
            "proposed_transformations": [],
            "rationale": "Future AI preprocessing assistant will propose transformations for scientist review.",
        },
    }
    _write_json(artifact_dir / "preprocessing_report.json", preprocessing_report)

    markdown = artifact_dir / "preprocessing_report.md"
    split_report["bo_replay"] = {
        "source": "train_validation_rows",
        "initial_observed_source": "train",
        "hidden_pool_source": "train_plus_validation_excluding_used_replay_ids",
        "test_policy": "untouched; reserved for model-quality evaluation only",
    }
    _write_json(artifact_dir / "split_report.json", split_report)

    markdown.write_text(
        "# Cell_01 Smoke Preprocessing Report\n\n"
        "This report is smoke/demo quality only and is not final scientific evidence.\n\n"
        f"Rows: {len(frame)}\n\n"
        f"Split counts: {eda_report['split_counts']}\n\n"
        "Future standard: grouped-by-cell splitting when all cells are implemented.\n",
        encoding="utf-8",
    )

    return {
        "artifact_dir": str(artifact_dir),
        "preprocessing_path": str(preprocessing_path),
        "schema_path": str(schema_path),
        "eda_report_path": str(artifact_dir / "eda_report.json"),
        "preprocessing_report_path": str(artifact_dir / "preprocessing_report.json"),
        "split_report_path": str(artifact_dir / "split_report.json"),
        "transformed_dataset_path": str(transformed_path),
        "row_count": int(len(frame)),
        "split_counts": eda_report["split_counts"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess audited Cell_01 real fuel-cell data for smoke ML training.")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--cell-id", default="Cell_01")
    parser.add_argument("--scope", choices=["cell_01_smoke", "all_cells"], default="all_cells")
    args = parser.parse_args()
    if args.scope == "cell_01_smoke" and args.cell_id != "Cell_01":
        raise ValueError("Cell_01 smoke preprocessing supports only Cell_01")
    result = build_preprocessing_artifacts(project_id=args.project_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
