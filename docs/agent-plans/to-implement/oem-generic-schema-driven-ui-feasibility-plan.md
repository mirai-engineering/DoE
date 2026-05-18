# OEM Generic Schema-Driven UI Feasibility Plan

## Context
The current app has grown from a PEM fuel-cell proof point into a broader ML-guided DoE/design engine. The user wants the product to support different OEMs, domains, test data, schemas, labels, axes, and plot conventions without hardcoded fuel-cell assumptions throughout the UI.

Initial scan confirms this is feasible but not a small cosmetic change. Fuel-cell specifics are mixed across frontend copy/plots and backend artifact helpers. Some pieces are already schema-driven (`schema.inputs`, `schema.outputs`, Model Map cards, objective weights), while other areas still assume PEM/cell/RH/voltage/current-density semantics.

## Approach
Move toward a project metadata contract where intake/training produces a portable `project_schema` plus approved `ui_config` / `plot_options`. Frontend pages should render from that contract, with generic fallbacks when a project has no domain-specific display metadata.

Recommended phased approach:
1. Inventory and classify hardcoded domain assumptions.
2. Define a schema/UI metadata contract for variables, roles, units, grouping, recommended plot recipes, comparison dimensions, and quality diagnostics.
3. Add Mirai-inferred metadata generation during intake/preprocessing, followed by admin approval before activation.
4. Add two MVP template packs: `fuel_cell` and `generic_tabular_doe`.
5. Add backend endpoints/artifact fields that expose approved metadata for uploaded projects.
6. Add an early `Plot Options` selector/dropdown driven by safe/recommended recipes. The selected/approved option locks what downstream pages plot/show for the project/session.
7. Refactor UI surfaces to use metadata first and fuel-cell-specific defaults only as one configured example.
8. Preserve specialized fuel-cell polarization behavior as a declarative plot recipe, not inline hardcoding.

## Files to modify
Likely affected files after feasibility/planning approval:

- `backend/app/services/project_registry.py`
- `backend/app/services/design_studio.py`
- `backend/app/services/model_quality.py`
- `backend/app/services/preprocessing_review.py`
- `backend/app/services/bayesian_optimization.py`
- `backend/training/real_training_pipeline/train_real_fuel_cell_models.py`
- `backend/training/real_data_pipeline/real_fuel_cell_schema.py`
- `frontend/src/types/doe.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/components/DesignStudioPage.tsx`
- `frontend/src/components/ModelQualityPage.tsx`
- `frontend/src/components/ModelMap.tsx`
- `frontend/src/components/BusinessImpactPage.tsx`
- `frontend/src/components/VisualizationsPage.tsx`
- `frontend/src/components/ResponseSurfaceHeatmap.tsx`
- `frontend/src/components/ParallelCoordinatesChart.tsx`
- `frontend/src/components/RecommendationsPage.tsx`
- `frontend/src/components/PredictPanel.tsx`
- `frontend/src/components/RecommendPanel.tsx`

## Reuse
Existing reusable foundations found:

- `schema.inputs` / `schema.outputs` already drive many UI controls and Model Map cards.
- `frontend/src/components/ModelMap.tsx` now uses schema-driven input/output cards and can remain generic with copy tweaks.
- `frontend/src/components/DesignStudioPage.tsx` uses schema outputs for objective presets and weights.
- `frontend/src/components/ParallelCoordinatesChart.tsx` appears generic enough to reuse dimensions from schema/recommendation rows.
- `frontend/src/components/PredictPanel.tsx` and `RecommendPanel.tsx` already render schema-driven inputs/outputs.
- `backend/app/services/project_registry.py` centralizes project schema/artifact resolution and is the right place to expose uploaded-project metadata.
- `backend/app/services/model_quality.py` already returns artifacts/metrics/predictions; it can include variable metadata and diagnostic plot options.
- `backend/app/services/design_studio.py` already exposes a `fuel_cell_preset`; this can become a generic `plot_recipes` / `curve_recipes` mechanism.

## Key findings so far

### Already partly generic
- Model Map cards are driven by `schema.inputs` and `schema.outputs`.
- Design Studio input controls and objective selection are mostly schema-driven.
- Prediction and recommendation panels use schema metadata.
- Output labels/units often come from schema.

### Fuel-cell-specific hotspots
- `frontend/src/components/DesignStudioPage.tsx`
  - Hardcoded response-curve copy: fuel-cell, voltage grid, BoL/EoL current density.
  - Hardcoded plot traces: `bol_current_density`, `eol_current_density`, `operating_voltage`.
  - Hardcoded measured overlay selector: real cell, RH, split.
  - Hardcoded balanced fuel-cell objective.
- `frontend/src/components/ModelQualityPage.tsx`
  - Defaults to `bol_current_density`, `cell_id`, RH, polarization rows.
  - Hardcoded cell/RH diagnostic filters and polarization plot wording.
  - Copy references all-cells MVP, BO holdout cells, cell-level partitions.
- `frontend/src/components/BusinessImpactPage.tsx`
  - Pitch copy is strongly fuel-cell specific: fuel-cell builds, CCM samples, polarization curves.
- `backend/app/services/design_studio.py`
  - Constants for `bol_current_density`, `eol_current_density`, `operating_voltage`, `operating_rh`.
  - Fuel-cell project detection and preset generation.
  - Real-cell comparison options assume `cell_id` and RH.
- `backend/app/services/model_quality.py`
  - Hardcoded output units and diagnostic fields.
  - Markdown/report copy references cells and all-cells workflow.
- `backend/app/services/preprocessing_review.py`
  - Current intake validation and preprocessing are fuel-cell-package-specific (`data_overview.xlsx`, `Cell_NN.zip`).
- `backend/app/services/project_registry.py`
  - Uploaded projects currently fall back to the base fuel-cell schema.
- `backend/app/services/bayesian_optimization.py`
  - Default objective weights include PEM/synthetic names.

## Proposed metadata contract
A future project schema should include more than input/output lists:

```json
{
  "project_id": "...",
  "display_name": "...",
  "domain": {
    "label": "Fuel cell" | "Battery" | "Catalyst" | "Generic tabular DoE",
    "test_article_label": "Cell" | "Sample" | "Part" | "Run"
  },
  "variables": [
    {
      "name": "operating_voltage",
      "label": "Cell voltage",
      "unit": "V",
      "role": "input" | "output" | "group" | "time" | "sweep" | "metadata",
      "semantic_type": "continuous" | "categorical" | "identifier",
      "direction": "maximize" | "minimize" | "target" | null,
      "recommended_plots": ["x_axis", "color", "facet", "filter"]
    }
  ],
  "ui_config": {
    "model_map": {
      "input_layer_label": "Controlled variables",
      "output_layer_label": "Predicted response"
    },
    "design_studio": {
      "primary_plot_recipe_id": "polarization_curve",
      "objective_presets": []
    },
    "model_quality": {
      "default_output": "...",
      "group_by_candidates": ["sample_id", "batch_id", "split"]
    }
  },
  "plot_recipes": [
    {
      "id": "polarization_curve",
      "label": "Dynamic response curve",
      "description": "...",
      "kind": "line",
      "x": { "source": "prediction", "variable": "bol_current_density" },
      "y": { "source": "input_sweep", "variable": "operating_voltage" },
      "series": []
    }
  ]
}
```

## Steps
- [ ] Complete hardcoded-label inventory across frontend/backend and classify as generic, project-configurable, or fuel-cell-only.
- [ ] Define `VariableMetadata`, `PlotRecipe`, `UiConfig`, `ProjectDomainMetadata`, and `TemplatePack` types.
- [ ] Extend preprocessing/intake to infer variable roles, labels, units, grouping candidates, safe/recommended plot recipes, and likely template (`fuel_cell` or `generic_tabular_doe`).
- [ ] Add admin approval state for inferred metadata; only approved metadata should drive downstream UI.
- [ ] Extend schema/artifact generation so approved metadata is written with training artifacts and project registry schema.
- [ ] Replace fuel-cell `design_studio.py` preset with generic `plot_recipes`, keeping the current PEM curve as the `fuel_cell` template recipe.
- [ ] Add early frontend `Plot Options` selector that shows safe/recommended recipes and locks the selected downstream plot/show configuration.
- [ ] Refactor Design Studio response curve to render the selected recipe/plot option instead of hardcoded BoL/EoL voltage traces.
- [ ] Refactor Model Quality diagnostics to use generic defaults: parity, residuals vs predicted, residuals by approved group, and metrics by output/split.
- [ ] Make domain-specific Model Quality plots optional recipe-driven add-ons.
- [ ] Make Business Impact generic/template-driven and remove fuel-cell-specific assumptions from default copy.
- [ ] Add migration fallback for existing PEM packaged project and current uploaded project, mapping them into the `fuel_cell` metadata template.
- [ ] Add tests for generic tabular DoE schema with non-fuel-cell variable names.

## Verification
- Existing PEM project still shows fuel-cell polarization curve via metadata recipe.
- Uploaded PEM project still resolves its schema/artifacts and shows identical or better curves.
- A synthetic generic project with arbitrary inputs/outputs shows:
  - generic Model Map labels,
  - generic Design Studio controls,
  - plot options rather than PEM-specific curve copy,
  - Model Quality diagnostics without cell/RH assumptions.
- Frontend build passes.
- Backend API tests cover project schema and plot recipe contract.

## User decisions captured
- Intake metadata source: Mirai should infer labels, units, variable roles, recommended plots, and template fit, then require admin approval before those semantics become active.
- Plot options UX: offer safe/recommended plot configurations only. This should appear early in the workflow as a dropdown/selection that locks what downstream pages plot/show for the project or session.
- Templates for MVP: support two template families now:
  - Fuel cell
  - Generic tabular DoE
  More OEM/domain templates can be added later as metadata packs.
- Business Impact: make it generic/template-driven for now. It may be removed or hidden in production later, but should not remain fuel-cell-specific.
- Model Quality diagnostics: use generic defaults for non-fuel-cell data:
  - predicted vs actual parity
  - residuals vs predicted
  - residuals by approved grouping variable
  - metric table by output and split
  Domain-specific plots appear only when approved metadata provides them.
- Backward compatibility: the current PEM fuel-cell project should remain the polished reference example, but implemented as the first metadata-driven domain configuration rather than inline hardcoding.

## Open questions for user
None blocking for the feasibility plan. Next implementation planning can refine exact metadata fields and UX copy.
