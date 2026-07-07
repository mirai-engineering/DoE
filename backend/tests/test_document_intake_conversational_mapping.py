from __future__ import annotations

import asyncio
from io import BytesIO

from starlette.datastructures import UploadFile

from app.services.document_intake import create_document_intake_session, match_mirai_contract, save_document_instruction, upload_document_intake_files


def test_generic_inventory_extracts_columns_and_contextual_approve_blockers(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    async def run_case():
        workspace_id = "test_ki_ws"
        project_id = "test_ki_project"
        session = create_document_intake_session(workspace_id, project_id, target_contract_id="generic_tabular_doe")
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
        assert "cannot approve everything" in draft["agent_response"].lower()
        assert "pt_c_ratio" in draft["agent_response"]
        assert draft["validation_result"]["blockers"]

    asyncio.run(run_case())


def test_generic_user_can_approve_complete_mapping_but_export_still_blocked(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    async def run_case():
        workspace_id = "test_ki_ws"
        project_id = "test_ki_project_constants"
        session = create_document_intake_session(workspace_id, project_id, target_contract_id="generic_tabular_doe")
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

        assert draft["status"] == "mapping_approved_blocked_executor"
        assert draft["validation_passed"] is False
        assert "deterministic transform executor" in " ".join(draft["validation_result"]["blockers"]).lower()

    asyncio.run(run_case())
