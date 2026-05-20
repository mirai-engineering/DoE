# Business Impact Reference Data Plan

## Context

The Business Impact tab currently mixes hardcoded PEM assumptions with repo-root data paths. The project cleanup direction is now stricter:

```text
immutable/reference evidence -> data/reference/
mutable app/object-store runtime state -> backend/data-minio/
active trained artifacts -> intake session artifacts or MLflow
```

Business Impact should follow the same project/artifact rules as Model Quality, Design Studio, prediction, and BO. It should not depend on loose root-level data files or legacy replay folders.

## Target Outcome

Refactor Business Impact into a project-aware, reference-backed feature:

- PEM reference evidence and source documents live under `data/reference/pem_fuel_cell_cathode_degradation/`.
- Mutable/customer/project ROI assumptions live under `backend/data-minio/business_impact/`.
- The backend resolves a business-impact profile by project ID.
- Projects without a configured profile show a clear "not configured yet" response instead of silently using PEM-specific assumptions.
- Repo-root obsolete data and replay artifacts can be deleted after migration.

## Proposed Data Layout

### Immutable PEM reference package

```text
data/reference/pem_fuel_cell_cathode_degradation/
  model_table.csv
  cell_metadata.csv
  ast_trace_manifest.csv
  business_impact_reference.json
  sources/
    PEM Fuel Cell Catalyst Optimization.pdf
```

`business_impact_reference.json` should hold reference-only values and source citations, for example:

```json
{
  "reference_id": "pem_fuel_cell_cathode_degradation",
  "title": "Fuel-cell Design of Experiments business impact",
  "paper_physical_cells": 49,
  "paper_polarization_curves": 294,
  "paper_data_points": 6700,
  "paper_full_characterization_hours_per_sample": 130.0,
  "sources": [
    {
      "label": "Reference PDF / Energy and AI 2024",
      "url": "data/reference/pem_fuel_cell_cathode_degradation/sources/PEM Fuel Cell Catalyst Optimization.pdf"
    }
  ]
}
```

### Mutable project impact profile

```text
backend/data-minio/business_impact/
  pem_fuel_cell_real_cathode_degradation.json
  <future_project_id>.json
```

Project profiles should hold mutable assumptions/scenarios, for example:

```json
{
  "project_id": "pem_fuel_cell_real_cathode_degradation",
  "reference_id": "pem_fuel_cell_cathode_degradation",
  "status": "configured",
  "scenario_name": "One 42-recipe catalyst-layer campaign",
  "virtual_candidates_per_screen": 2000,
  "target_experiment_reduction_fraction": 0.35,
  "hands_on_hours_per_physical_sample": 6.0,
  "internal_direct_cost_per_sample_usd": [1500, 3000],
  "external_testbed_day_rate_usd": [3000, 5000]
}
```

## Implementation Steps

1. **Add business-impact profile models**
   - Define small typed helpers in `backend/app/services/business_impact.py` or a new `business_impact_profiles.py`.
   - Validate required fields for reference profiles and project profiles.
   - Keep schema permissive enough for future non-PEM customer projects.

2. **Move PEM source evidence under reference data**
   - Move the PEM PDF from repo-root `data/` into:

     ```text
     data/reference/pem_fuel_cell_cathode_degradation/sources/
     ```

   - Add `business_impact_reference.json` next to the existing PEM reference CSVs.
   - Update source URLs returned by the API to point at the new reference location.

3. **Add mutable project profile storage**
   - Create:

     ```text
     backend/data-minio/business_impact/pem_fuel_cell_real_cathode_degradation.json
     ```

   - Store scenario assumptions there instead of hardcoding them in service constants.
   - Keep this file as app/runtime state, not immutable reference evidence.

4. **Refactor Business Impact resolver**
   - Resolve impact data in this order:

     ```text
     1. backend/data-minio/business_impact/<project_id>.json
     2. data/reference/<reference_id>/business_impact_reference.json
     3. active project artifacts where relevant
     ```

   - Use `model_table.csv`, `cell_metadata.csv`, and `ast_trace_manifest.csv` from the resolved reference package when `reference_id` is configured.
   - Avoid reading loose root-level files.

5. **Handle unconfigured projects cleanly**
   - For new generic Fraunhofer/Mirai projects without an impact profile, return a clear not-configured response such as:

     ```json
     {
       "project_id": "...",
       "status": "not_configured",
       "message": "Business impact assumptions have not been configured for this project yet."
     }
     ```

   - Update the frontend Business Impact tab to display this as an empty-state card instead of an error.

6. **Preserve current PEM user experience**
   - The existing PEM Business Impact visuals and takeaways should remain functionally equivalent after the data move.
   - Only the storage/resolution source should change.

7. **Clean obsolete root data only after validation**
   - Delete or move only after confirming no backend/frontend/tests reference them:

     ```text
     data/replay/
     data/PEM Fuel Cell Catalyst Optimization.pdf
     ```

   - Review before deleting larger raw/reference folders:

     ```text
     data/Cathode Catalyst Degradation/
     data/AI Design Gas Diffusion Layers for Fuel Cells.pdf
     ```

   - Keep `data/reference/` as the canonical immutable reference root.

8. **Update documentation**
   - Document the split:

     ```text
     data/reference/ = immutable/reference evidence
     backend/data-minio/business_impact/ = mutable per-project scenario assumptions
     ```

   - Update any Business Impact or PEM reference docs that mention root-level data files.

9. **Add validation/tests**
   - Add backend tests for:
     - PEM configured profile returns the existing summary shape.
     - Unknown/unconfigured project returns not-configured response.
     - Resolver does not require repo-root PDF/replay files.
   - Add/update frontend test or build validation for the not-configured empty state.

## Non-Goals

- Do not implement a full Business Impact admin editor yet.
- Do not create customer-specific Python packages.
- Do not make Business Impact generic ROI math mandatory for every uploaded project.
- Do not move mutable project assumptions into `data/reference/`.
- Do not reintroduce `backend/artifacts/`, `runtime-projects/`, or replay CSV fallback folders.

## Validation Commands

```bash
cd backend && uv run pytest tests/test_api.py -q
cd frontend && npm run build
```

If new backend tests are added for Business Impact:

```bash
cd backend && uv run pytest tests/test_api.py tests/test_business_impact.py -q
```

## Rollout Notes

- Implement after the active artifact resolver work, or at least align naming with it.
- Keep PEM reference behavior stable first, then enable clean empty states for new generic projects.
- After validation, remove only the confirmed-unused root-level files/folders.
