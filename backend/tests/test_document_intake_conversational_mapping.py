from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
import zipfile

from starlette.datastructures import UploadFile

from app.services.document_intake import (
    approve_draft_table,
    create_document_intake_session,
    export_mirai_package,
    match_mirai_contract,
    save_document_instruction,
    upload_document_intake_files,
    upload_document_intake_target_contract,
)

EXAMPLE_CONTRACT = Path(__file__).resolve().parents[1] / "docs" / "examples" / "fuel-cell" / "fraunhofer2miraicontract-cell-01"


def _zip_model_table_contract() -> bytes:
    manifest = {
        "manifest_version": "0.2",
        "project": {"template_id": "generic_tabular_doe", "display_name": "Generic custom target"},
        "tables": [{"path": "model_table.csv", "primary_key": ["row_id"]}],
        "columns": [
            {"table": "model_table.csv", "source_name": "row_id", "variable_id": "row_id", "role": "id", "dtype": "string", "required": True},
            {"table": "model_table.csv", "source_name": "temperature_c", "variable_id": "x1", "role": "input", "dtype": "float", "unit": "degC", "required": True, "ui_label": "Temperature"},
            {"table": "model_table.csv", "source_name": "yield_pct", "variable_id": "y1", "role": "output", "dtype": "float", "unit": "%", "direction": "maximize", "required": True, "ui_label": "Yield"},
        ],
    }
    dictionary = "table,source_name,variable_id,ui_label,role,dtype,unit,required,direction,description\nmodel_table.csv,row_id,row_id,Row ID,id,string,,true,,\nmodel_table.csv,temperature_c,x1,Temperature,input,float,degC,true,,\nmodel_table.csv,yield_pct,y1,Yield,output,float,%,true,maximize,\n"
    model_table = "row_id,temperature_c,yield_pct\nr1,80,42\nr2,85,45\n"
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mirai_manifest.json", __import__("json").dumps(manifest))
        archive.writestr("data_dictionary.csv", dictionary)
        archive.writestr("model_table.csv", model_table)
    return buffer.getvalue()


def _zip_example_contract(*, include_tables: bool = True) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in EXAMPLE_CONTRACT.iterdir():
            if path.name.endswith(".csv") or path.name == "mirai_manifest.json":
                if not include_tables and path.name not in {"mirai_manifest.json", "data_dictionary.csv"}:
                    continue
                archive.write(path, arcname=path.name)
    return buffer.getvalue()


async def _session_with_target(workspace_id: str, project_id: str) -> dict:
    session = create_document_intake_session(workspace_id, project_id, target_contract_id="generic_tabular_doe")
    await upload_document_intake_target_contract(
        workspace_id,
        project_id,
        session["id"],
        [UploadFile(filename="target_contract.zip", file=BytesIO(_zip_example_contract()))],
    )
    return session


def test_generic_inventory_extracts_columns_from_uploaded_target_contract(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def run_case():
        workspace_id = "test_ki_ws"
        project_id = "test_ki_project_uploaded_target"
        session = await _session_with_target(workspace_id, project_id)
        csv_bytes = b"operating_voltage,operating_rh,current_density,ecsa\n0.6,80,1.2,50\n"

        await upload_document_intake_files(
            workspace_id,
            project_id,
            session["id"],
            [UploadFile(filename="sample.csv", file=BytesIO(csv_bytes))],
        )
        save_document_instruction(workspace_id, project_id, session["id"], "approve everything")

        result = match_mirai_contract(workspace_id, project_id, session["id"])
        draft = result["draft"]

        assert draft["validation_passed"] is False
        assert draft["available_columns"]
        assert {column["column"] for column in draft["available_columns"]} >= {"operating_voltage", "operating_rh", "current_density", "ecsa"}
        assert len(draft["mapping_board"]) >= 4
        assert {row["variable_id"] for row in draft["mapping_board"] if row.get("role") == "input"} >= {"x1", "x2", "x3"}
        assert any(row.get("source_name") == "pt_c_ratio" for row in draft["mapping_board"])
        assert "cannot approve everything" in draft["agent_response"].lower()
        assert "x1" in draft["agent_response"] or "pt_c_ratio" in draft["agent_response"]
        assert draft["validation_result"]["blockers"]

    asyncio.run(run_case())


def test_generic_user_can_approve_complete_mapping_but_export_still_blocked_without_package_tables(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def run_case():
        workspace_id = "test_ki_ws"
        project_id = "test_ki_project_constants_uploaded_target"
        session = await _session_with_target(workspace_id, project_id)
        csv_bytes = b"pt_c_ratio,i_c_ratio,ionomer_ew,operating_voltage,operating_rh,ast_rh,ast_upl,bol_current_density,eol_current_density,bol_ecsa,ecsa_loss\n0.4,0.9,1100,0.6,80,100,0.95,1.1,0.9,50,5\n"

        await upload_document_intake_files(
            workspace_id,
            project_id,
            session["id"],
            [UploadFile(filename="complete.csv", file=BytesIO(csv_bytes))],
        )
        save_document_instruction(workspace_id, project_id, session["id"], "approve suggested mapping")

        result = match_mirai_contract(workspace_id, project_id, session["id"])
        draft = result["draft"]

        assert draft["status"] in {"mapping_approved_blocked_executor", "needs_user_input"}
        assert draft["validation_passed"] is False
        assert draft["validation_result"]["status"] == "blocked_no_validated_transform"
        assert draft["validation_result"]["transform_attempt"]["status"] == "source_package_tables_missing"

    asyncio.run(run_case())


def test_different_uploaded_model_table_target_does_not_use_fuel_cell_fields(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def run_case():
        workspace_id = "test_ki_ws"
        project_id = "test_ki_project_custom_model_table"
        session = create_document_intake_session(workspace_id, project_id, target_contract_id="generic_tabular_doe")
        await upload_document_intake_target_contract(
            workspace_id,
            project_id,
            session["id"],
            [UploadFile(filename="custom_target.zip", file=BytesIO(_zip_model_table_contract()))],
        )
        await upload_document_intake_files(
            workspace_id,
            project_id,
            session["id"],
            [UploadFile(filename="model_table.csv", file=BytesIO(b"row_id,temperature_c,yield_pct\nr1,80,42\nr2,85,45\n"))],
        )
        save_document_instruction(workspace_id, project_id, session["id"], "approve suggested mapping")

        result = match_mirai_contract(workspace_id, project_id, session["id"])
        draft = result["draft"]
        fields = {row["source_name"] for row in draft["mapping_board"]}
        assert {"temperature_c", "yield_pct"}.issubset(fields)
        assert "pt_c_ratio" not in fields
        assert draft["validation_passed"] is True
        assert set(draft["contract_files"]) == {"mirai_manifest.json", "data_dictionary.csv", "model_table.csv"}

    asyncio.run(run_case())


def test_uploaded_target_contract_package_tables_can_validate_and_export(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def run_case():
        workspace_id = "test_ki_ws"
        project_id = "test_ki_project_package_tables"
        session = await _session_with_target(workspace_id, project_id)
        source_uploads = []
        for name in ["experiments.csv", "conditions.csv", "results.csv"]:
            source_uploads.append(UploadFile(filename=name, file=BytesIO((EXAMPLE_CONTRACT / name).read_bytes())))

        await upload_document_intake_files(workspace_id, project_id, session["id"], source_uploads)
        save_document_instruction(workspace_id, project_id, session["id"], "approve suggested mapping")

        result = match_mirai_contract(workspace_id, project_id, session["id"])
        draft = result["draft"]
        assert draft["validation_passed"] is True
        assert draft["contract_files"]
        assert {"mirai_manifest.json", "data_dictionary.csv", "experiments.csv", "conditions.csv", "results.csv"}.issubset(draft["contract_files"])

        approve_draft_table(workspace_id, project_id, session["id"], approved_by="test")
        export = export_mirai_package(workspace_id, project_id, session["id"])
        assert export["status"] == "exported"
        assert export["package_key"].endswith("/exports/mirai_package.zip")

    asyncio.run(run_case())
