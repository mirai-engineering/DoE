from app.services import project_registry


def test_runtime_control_plane_project_schema_resolves_without_reference_artifacts(monkeypatch):
    project_registry.get_project_schema.cache_clear()

    def fake_runtime_state(workspace_id: str, project_id: str):
        assert workspace_id == "fraunhofer"
        assert project_id == "pem_fuel_cell_real_cathode_degradation"
        return {
            "project": {
                "project_id": project_id,
                "workspace_id": workspace_id,
                "workspace_name": "Fraunhofer",
                "display_name": "PEM Fuel Cell Cathode Degradation",
                "lifecycle_contract": "generic_tabular_doe",
                "schema_version": "railway-runtime-v1",
            },
            "schema_manifest": {
                "schema_id": "schema_fraunhofer_fuel_cell_seed_v1",
                "input_columns": ["pt_c_ratio", "operating_voltage"],
                "output_columns": ["bol_current_density", "ecsa_loss"],
                "unit_map": {"operating_voltage": "V"},
                "schema_json": {"project_id": project_id, "source": "seeded_training_artifacts_latest"},
            },
        }

    monkeypatch.setattr(project_registry, "get_project_runtime_state", fake_runtime_state)

    schema = project_registry.get_project_schema("pem_fuel_cell_real_cathode_degradation", "fraunhofer")

    assert schema["project_id"] == "pem_fuel_cell_real_cathode_degradation"
    assert schema["workspace_id"] == "fraunhofer"
    assert schema["workspace_name"] == "Fraunhofer"
    assert schema["display_name"] == "PEM Fuel Cell Cathode Degradation"
    assert [item["name"] for item in schema["inputs"]] == ["pt_c_ratio", "operating_voltage"]
    assert [item["name"] for item in schema["outputs"]] == ["bol_current_density", "ecsa_loss"]
    assert schema["inputs"][1]["unit"] == "V"
    assert schema["domain_metadata"]["approval_status"] == "approved"
