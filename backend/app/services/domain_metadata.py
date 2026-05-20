from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, TypedDict


VariableRole = Literal["id", "input", "output", "group", "sweep", "time", "cycle", "sequence", "curve_axis", "metadata", "context", "ignore"]
TemplateId = Literal["fuel_cell", "generic_tabular_doe"]


class VariableMetadata(TypedDict, total=False):
    name: str
    label: str
    unit: str
    role: VariableRole
    semantic_type: str
    direction: str | None
    min: float | None
    max: float | None
    approved: bool
    recommended_plot_roles: list[str]


class PlotRecipe(TypedDict, total=False):
    id: str
    label: str
    description: str
    kind: str
    template_id: str
    safe: bool
    recommended: bool
    x: dict[str, Any]
    y: dict[str, Any]
    series: list[dict[str, Any]]
    group_by: str | None
    filters: list[str]


class UiConfig(TypedDict, total=False):
    selected_plot_recipe_id: str
    plot_recipes: list[PlotRecipe]
    model_quality: dict[str, Any]
    design_studio: dict[str, Any]
    business_impact: dict[str, Any]


class ProjectDomainMetadata(TypedDict, total=False):
    template_id: TemplateId
    label: str
    test_article_label: str
    inferred: bool
    approval_status: str
    approved_by: str | None
    variables: list[VariableMetadata]
    ui_config: UiConfig


FUEL_CELL_INPUT_ROLES = {
    "operating_voltage": "sweep",
    "operating_rh": "group",
}

FUEL_CELL_LABELS = {
    "pt_c_ratio": "Pt/C ratio",
    "i_c_ratio": "I/C ratio",
    "ionomer_ew": "Ionomer equivalent weight",
    "operating_rh": "Operating relative humidity",
    "operating_voltage": "Operating voltage",
    "ast_rh": "AST relative humidity",
    "ast_upl": "AST upper potential limit",
    "bol_current_density": "BoL current density",
    "eol_current_density": "EoL current density",
    "bol_ecsa": "BoL ECSA",
    "ecsa_loss": "ECSA loss",
    "cell_id": "Cell ID",
    "split": "Data split",
}

FUEL_CELL_UNITS = {
    "operating_rh": "%",
    "operating_voltage": "V",
    "ast_rh": "%",
    "ast_upl": "V",
    "bol_current_density": "A/cm²",
    "eol_current_density": "A/cm²",
    "bol_ecsa": "cm²/cm²",
    "ecsa_loss": "fraction",
}


def _variable_from_schema(item: dict[str, Any], role: VariableRole) -> VariableMetadata:
    name = str(item.get("name", ""))
    return {
        "name": name,
        "label": str(item.get("label") or FUEL_CELL_LABELS.get(name) or name.replace("_", " ").title()),
        "unit": str(item.get("unit") or FUEL_CELL_UNITS.get(name) or ""),
        "role": FUEL_CELL_INPUT_ROLES.get(name, role) if role == "input" else role,
        "semantic_type": str(item.get("type") or "continuous"),
        "direction": item.get("direction"),
        "min": item.get("min"),
        "max": item.get("max"),
        "approved": True,
    }


def infer_template_id(schema: dict[str, Any], columns: list[str] | None = None) -> TemplateId:
    names = {item.get("name") for item in schema.get("inputs", []) + schema.get("outputs", [])}
    names.update(columns or [])
    fuel_cell_markers = {"operating_voltage", "bol_current_density", "eol_current_density", "ecsa_loss", "cell_id", "operating_rh"}
    return "fuel_cell" if len(names.intersection(fuel_cell_markers)) >= 3 else "generic_tabular_doe"


def fuel_cell_plot_recipes() -> list[PlotRecipe]:
    return [
        {
            "id": "fuel_cell_polarization_curve",
            "label": "Dynamic response curve",
            "description": "Uses the observed voltage grid and predicts BoL/EoL current density at each voltage.",
            "kind": "fuel_cell_polarization",
            "template_id": "fuel_cell",
            "safe": True,
            "recommended": True,
            "x": {"source": "prediction", "variables": ["bol_current_density", "eol_current_density"], "label": "Current density", "unit": "A/cm²"},
            "y": {"source": "input_sweep", "variable": "operating_voltage", "label": "Cell voltage", "unit": "V"},
            "series": [
                {"label": "BoL", "variable": "bol_current_density"},
                {"label": "EoL", "variable": "eol_current_density"},
            ],
            "group_by": "cell_id",
            "filters": ["operating_rh", "split"],
        }
    ]


def generic_plot_recipes(schema: dict[str, Any]) -> list[PlotRecipe]:
    outputs = schema.get("outputs", [])
    inputs = schema.get("inputs", [])
    first_output = outputs[0].get("name") if outputs else None
    first_input = inputs[0].get("name") if inputs else None
    recipes: list[PlotRecipe] = []
    if first_output:
        recipes.append(
            {
                "id": f"parity_{first_output}",
                "label": "Predicted vs actual",
                "description": "Safe model-quality parity plot for the selected output.",
                "kind": "parity",
                "template_id": "generic_tabular_doe",
                "safe": True,
                "recommended": True,
                "x": {"source": "artifact", "variable": f"{first_output}_true"},
                "y": {"source": "artifact", "variable": f"{first_output}_pred"},
                "series": [],
                "group_by": None,
                "filters": ["split"],
            }
        )
    if first_input and first_output:
        recipes.append(
            {
                "id": f"response_{first_input}_{first_output}",
                "label": "Output response by input",
                "description": "Recommended generic line/scatter view of one model output against one input variable.",
                "kind": "scatter_response",
                "template_id": "generic_tabular_doe",
                "safe": True,
                "recommended": True,
                "x": {"source": "input", "variable": first_input},
                "y": {"source": "prediction", "variable": first_output},
                "series": [],
                "group_by": None,
                "filters": [],
            }
        )
    return recipes


def build_domain_metadata(schema: dict[str, Any], *, template_id: TemplateId | None = None, approval_status: str = "approved") -> ProjectDomainMetadata:
    template = template_id or infer_template_id(schema)
    variables: list[VariableMetadata] = []
    variables.extend(_variable_from_schema(item, "input") for item in schema.get("inputs", []))
    variables.extend(_variable_from_schema(item, "output") for item in schema.get("outputs", []))
    metadata_variables = schema.get("metadata", {}).get("variables", []) if isinstance(schema.get("metadata"), dict) else []
    for item in metadata_variables:
        if isinstance(item, dict):
            variables.append(_variable_from_schema(item, item.get("role") or "metadata"))
    if template == "fuel_cell":
        variables.append({"name": "cell_id", "label": "Cell ID", "unit": "", "role": "group", "semantic_type": "identifier", "approved": True})
        variables.append({"name": "split", "label": "Data split", "unit": "", "role": "metadata", "semantic_type": "categorical", "approved": True})
        recipes = fuel_cell_plot_recipes()
        selected = "fuel_cell_polarization_curve"
        label = "Fuel cell"
        test_article_label = "Cell"
        model_quality = {
            "default_output": "bol_current_density",
            "default_group": "cell_id",
            "default_residual_x": "operating_voltage",
            "diagnostics": ["parity", "residuals_vs_x", "residuals_by_group", "fuel_cell_polarization"],
        }
    else:
        recipes = generic_plot_recipes(schema)
        selected = recipes[0]["id"] if recipes else ""
        label = "Generic tabular DoE" if template == "generic_tabular_doe" else "Custom tabular"
        metadata = schema.get("metadata", {}) if isinstance(schema.get("metadata"), dict) else {}
        test_article_label = str(metadata.get("ui_config", {}).get("test_article_label") or "Sample") if isinstance(metadata.get("ui_config"), dict) else "Sample"
        group_candidates = [item.get("name") for item in metadata_variables if isinstance(item, dict) and item.get("role") in {"group", "id"}]
        model_quality = {
            "default_output": schema.get("outputs", [{}])[0].get("name", "") if schema.get("outputs") else "",
            "default_group": group_candidates[0] if group_candidates else "split",
            "default_residual_x": "predicted",
            "diagnostics": ["parity", "residuals_vs_predicted", "residuals_by_group", "metrics_by_output_split"],
        }
    return {
        "template_id": template,
        "label": label,
        "test_article_label": test_article_label,
        "inferred": True,
        "approval_status": approval_status,
        "approved_by": "Mirai default migration" if approval_status == "approved" else None,
        "variables": variables,
        "ui_config": {
            "selected_plot_recipe_id": selected,
            "plot_recipes": recipes,
            "model_quality": model_quality,
            "design_studio": {"primary_plot_recipe_id": selected, "objective_presets": []},
            "business_impact": {"template_id": template, "generic_default": template != "fuel_cell"},
        },
    }


def apply_variable_metadata_to_schema(schema: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(schema)
    metadata = enriched.get("domain_metadata") if isinstance(enriched.get("domain_metadata"), dict) else {}
    variables = metadata.get("variables") if isinstance(metadata.get("variables"), list) else []
    by_name = {item.get("name"): item for item in variables if isinstance(item, dict) and item.get("name")}
    for section in ("inputs", "outputs"):
        next_items = []
        for item in enriched.get(section, []):
            variable = by_name.get(item.get("name"))
            if isinstance(variable, dict):
                updated = dict(item)
                if variable.get("label"):
                    updated["label"] = variable["label"]
                if "unit" in variable:
                    updated["unit"] = variable.get("unit") or ""
                if variable.get("role"):
                    updated["role"] = variable["role"]
                next_items.append(updated)
            else:
                next_items.append(item)
        enriched[section] = next_items
    return enriched


def attach_domain_metadata(schema: dict[str, Any], *, template_id: TemplateId | None = None, approval_status: str = "approved") -> dict[str, Any]:
    enriched = deepcopy(schema)
    existing = enriched.get("domain_metadata")
    if isinstance(existing, dict) and existing.get("approval_status") == "approved":
        return apply_variable_metadata_to_schema(enriched)
    enriched["domain_metadata"] = build_domain_metadata(enriched, template_id=template_id, approval_status=approval_status)
    return apply_variable_metadata_to_schema(enriched)
