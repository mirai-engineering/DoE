from __future__ import annotations

from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from zipfile import BadZipFile, ZipFile

from ml_lifecycle.ingesting.fuel_cell_doe_demo.ingest import BuildPaths, build_all_cells
from ml_lifecycle.ingesting.fuel_cell_doe_demo.schema import SOURCE_PDF
from ml_lifecycle.ingesting.generic_tabular_doe.contract import ContractValidationError


def _is_metadata_zip_member(name: str) -> bool:
    parts = Path(name).parts
    return not parts or parts[0] == "__MACOSX" or any(part == ".DS_Store" for part in parts) or Path(name).name.startswith("._")


def _safe_zip_target(root: Path, member_name: str) -> Path:
    normalized = Path(member_name)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ContractValidationError([f"Unsafe zip member path: {member_name}"])
    target = (root / normalized).resolve()
    root_resolved = root.resolve()
    if root_resolved not in [target, *target.parents]:
        raise ContractValidationError([f"Zip member escapes extraction root: {member_name}"])
    return target


def _archive_paths(raw_root: Path, patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(sorted(raw_root.glob(pattern)))
        if "/" in pattern or "\\" in pattern:
            paths.extend(sorted(raw_root.glob(Path(pattern).name)))
    return sorted({path.resolve(): path for path in paths if path.is_file() and path.suffix.lower() == ".zip"}.values())


def _extract_cell_zip(zip_path: Path, extract_root: Path) -> dict[str, Any]:
    match = re.fullmatch(r"Cell_(\d{2})\.zip", zip_path.name)
    if not match:
        raise ContractValidationError([f"PEM raw extractor expected Cell_NN.zip archive, got {zip_path.name}"])
    cell_id = f"Cell_{match.group(1)}"
    data_root = extract_root / "01-Data"
    cell_root = data_root / cell_id
    extracted_file_count = 0
    extracted_preview: list[str] = []
    skipped_members: list[str] = []
    try:
        with ZipFile(zip_path) as archive:
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                if member.is_dir() or _is_metadata_zip_member(name):
                    skipped_members.append(name)
                    continue
                parts = Path(name).parts
                relative = Path(*parts) if parts and parts[0] == cell_id else Path(cell_id) / Path(name)
                target = _safe_zip_target(data_root, str(relative))
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                extracted_file_count += 1
                if len(extracted_preview) < 20:
                    extracted_preview.append(str(target.resolve().relative_to(extract_root.resolve())))
    except BadZipFile as exc:
        raise ContractValidationError([f"Invalid zip archive: {zip_path.name}"]) from exc
    return {"archive": zip_path.name, "cell_id": cell_id, "target_dir": str(cell_root.relative_to(extract_root)), "file_count": extracted_file_count, "files_preview": extracted_preview, "skipped_member_count": len(skipped_members), "skipped_members_preview": skipped_members[:20]}


def run_pem_cell_zip_bundle(*, raw_root: Path, canonical_dir: Path, artifact_dir: Path, extractor: dict[str, Any], index: int) -> tuple[str, Path, dict[str, Any]]:
    overview = raw_root / str(extractor.get("overview_workbook") or "data_overview.xlsx")
    if not overview.exists():
        raise ContractValidationError([f"PEM raw extractor missing overview workbook: {overview.name}"])
    archive_globs = [str(item) for item in extractor.get("archive_globs", ["Cell_*.zip"]) if str(item).strip()]
    cell_zips = _archive_paths(raw_root, archive_globs)
    if not cell_zips:
        raise ContractValidationError([f"PEM raw extractor found no Cell_NN.zip archives for glob(s): {archive_globs}"])
    # The PEM builder needs extracted Cell_NN.zip contents, but those raw CSVs are
    # intermediate working files only. Keep them in a temporary directory so training
    # artifacts do not explode into thousands of raw CSV files.
    with tempfile.TemporaryDirectory(prefix=f"mirai_pem_extractor_{index}_") as tmpdir:
        workspace = Path(tmpdir)
        overview_dir = workspace / "02-Testing_overview"
        overview_dir.mkdir(parents=True, exist_ok=True)
        workbook_target = overview_dir / "data_overview.xlsx"
        workbook_target.write_bytes(overview.read_bytes())
        extraction_results = [_extract_cell_zip(path, workspace) for path in cell_zips]
        build_dir = canonical_dir / "raw_extractor_outputs" / f"extractor_{index}"
        build_result = build_all_cells(
            BuildPaths(source_root=workspace, cell_data_root=workspace / "01-Data", workbook_path=workbook_target, output_dir=build_dir, source_pdf=SOURCE_PDF),
            dry_run=False,
            cell_ids=sorted({result["cell_id"] for result in extraction_results}),
        )
    output_table = str(extractor.get("output_table") or "model_table.csv")
    generated_table_path = build_dir / output_table
    if not generated_table_path.exists():
        raise ContractValidationError([f"PEM raw extractor did not generate expected table: {output_table}"])
    report = {"kind": "pem_cell_zip_bundle", "output_table": output_table, "generated_table": str(generated_table_path), "archive_count": len(cell_zips), "cell_ids": sorted({result["cell_id"] for result in extraction_results}), "row_counts": build_result.row_counts, "extraction_summary": extraction_results}
    return output_table, generated_table_path, report
