# Design Studio Pareto Tradeoff Search Plan

## Context

Design Studio currently supports a single-starting-design search:

```text
Find best starting design
```

It samples many virtual candidates, predicts them with the served model, scores them using selected objective weights, and loads the highest-scoring candidate into the playground.

This works for single-objective exploration, but scientists often need to reason about tradeoffs:

```text
high BoL current density
high EoL current density
low ECSA loss
reasonable ECSA retention
```

A weighted score hides those tradeoffs. A Pareto search should instead return a set of non-dominated candidates, where no returned candidate is clearly worse than another across all selected objectives.

The UI should keep the default simple:

```text
single objective / Find best starting design
```

and add a second action:

```text
Find Pareto tradeoffs
```

The heatmap feature from the previous roadmap is not implemented yet. It should remain a follow-up item after Pareto search unless explicitly bundled later.

## Approach

Add a Pareto tradeoff mode to Design Studio:

1. User selects multiple objective outputs/weights in the existing Optimization goal panel.
2. User clicks `Find Pareto tradeoffs`.
3. Backend samples candidates, predicts outputs, converts selected objectives into “higher is better” space, computes the non-dominated frontier, selects representative candidates, and returns them.
4. Frontend displays Pareto candidate cards and a simple 2D/3D-style tradeoff plot when possible.
5. User clicks `Load into playground` on a Pareto candidate, which updates sliders, predictions, and the dynamic curve.

Keep this schema-driven and future-project-ready.

## Files to modify

Backend:

```text
backend/app/services/design_studio.py
backend/app/main.py
```

Frontend:

```text
frontend/src/lib/api.ts
frontend/src/components/DesignStudioPage.tsx
```

Tests:

```text
backend/tests/test_real_fuel_cell_data_pipeline.py
```

Docs:

```text
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
```

Optional later:

```text
docs/agent-plans/design-studio-heatmap-plan.md
```

## Reuse

Reuse existing backend components:

```text
_generate_candidates(...)
_score_predictions(...)
predict_rows(...)
predict_design(...)
```

Reuse existing frontend state:

```text
objectiveMode
objectiveWeights
selectedObjectiveWeights
inputs
prediction
savedComparison
selectedRealCellPayload
```

Reuse schema metadata:

```text
schema.outputs[].name
schema.outputs[].label
schema.outputs[].direction
schema.outputs[].unit
```

## Step 1 — Add Pareto backend helper

In `backend/app/services/design_studio.py`, add helper functions:

```python
_selected_objectives(schema, objective_weights) -> list[dict]
_objective_matrix(predictions, objectives) -> np.ndarray
_non_dominated_mask(matrix) -> np.ndarray
_select_representative_pareto_candidates(...) -> list[int]
```

Rules:

- Ignore objectives with zero weight.
- For maximize outputs:
  ```text
  transformed value = prediction value
  ```
- For minimize outputs:
  ```text
  transformed value = -prediction value
  ```
- For custom weights, use the sign of the weight as user intent:
  ```text
  positive = larger is better
  negative = smaller is better
  ```
- Normalize objectives before choosing representatives so one unit scale does not dominate diversity selection.

## Step 2 — Add Pareto search service function

Add:

```python
pareto_tradeoff_candidates(project_id: str, payload: dict[str, Any]) -> dict[str, Any]
```

Input payload:

```json
{
  "objective_weights": {
    "bol_current_density": 0.4,
    "eol_current_density": 0.4,
    "ecsa_loss": -0.2
  },
  "fixed_inputs": {},
  "constraints": {},
  "n_candidates": 3000,
  "max_results": 12,
  "comparison_real_cell": null
}
```

Response:

```json
{
  "project_id": "...",
  "source": "pareto_tradeoff_search",
  "model_version": "...",
  "objective_weights": {...},
  "objectives": [
    {"name": "bol_current_density", "direction": "maximize", "weight": 0.4, "unit": "A/cm²"}
  ],
  "n_candidates": 3000,
  "pareto_count": 184,
  "returned_count": 12,
  "candidates": [
    {
      "rank": 1,
      "label": "High BoL current density",
      "inputs": {...},
      "predictions": {...},
      "score": 0.91,
      "tradeoff_summary": "Strong BoL current density with moderate ECSA loss."
    }
  ],
  "warnings": []
}
```

Candidate labels should be simple and data-driven:

- highest value for a positive/maximize objective:
  ```text
  High {output label}
  ```
- best value for a minimize/negative objective:
  ```text
  Low {output label}
  ```
- otherwise:
  ```text
  Balanced tradeoff
  ```

## Step 3 — Add backend endpoint

Add endpoint:

```text
POST /projects/{project_id}/design-studio/pareto
```

It should call:

```python
pareto_tradeoff_candidates(...)
```

## Step 4 — Add tests

Extend `test_model_quality_api_contracts` or add a focused test in:

```text
backend/tests/test_real_fuel_cell_data_pipeline.py
```

Assert:

- endpoint returns 200
- `source == pareto_tradeoff_search`
- candidates are non-empty
- candidates include inputs and predictions
- `pareto_count >= returned_count`
- selected objectives are reported

## Step 5 — Add frontend API type/function

In `frontend/src/lib/api.ts`, add:

```ts
export interface DesignStudioParetoResponse { ... }
export async function findDesignStudioPareto(projectId, request): Promise<DesignStudioParetoResponse>
```

## Step 6 — Add Pareto button and loading state

In `DesignStudioPage.tsx`, add state:

```ts
const [paretoLoading, setParetoLoading] = useState(false)
const [paretoResults, setParetoResults] = useState<DesignStudioParetoResponse | null>(null)
```

Add button next to existing action:

```text
Find Pareto tradeoffs
```

Plain-language copy:

```text
Use this when you care about several outputs at once. Instead of one winner, the app returns candidate designs that represent different tradeoffs.
```

Disable or warn if fewer than two non-zero objectives are selected:

```text
Select at least two non-zero objectives for Pareto tradeoffs.
```

## Step 7 — Display Pareto tradeoff candidates

Add a new panel below live predictions or below the curve:

```text
Pareto tradeoff candidates
```

Each card shows:

```text
candidate label
predicted objective outputs
small tradeoff summary
Load into playground button
```

When user clicks `Load into playground`:

1. Set `inputs` to the candidate inputs.
2. Call `predictDesignStudio(...)` for that candidate.
3. Update curve and output cards.

## Step 8 — Add simple Pareto plot

If there are at least two selected objectives, show a scatter plot:

```text
x = first selected objective
y = second selected objective
color/marker = third selected objective if available
```

For minimize objectives, label clearly whether plotted values are raw prediction values or transformed optimization direction.

Recommendation: plot raw prediction values with clear axis labels:

```text
BoL current density / A cm⁻²
ECSA loss / fraction
```

Add note:

```text
For minimized objectives, lower on the axis is better.
```

This avoids confusing scientists with transformed negative values.

## Step 9 — Improve explanations for non-ML users

Add copy:

```text
Pareto tradeoffs are useful when there is no single obvious best design. A candidate is on the Pareto frontier when another candidate cannot improve one selected objective without making at least one other selected objective worse.
```

Add caution:

```text
Pareto candidates are model-proposed options for discussion. They are not lab-confirmed optima.
```

## Step 10 — Update tutorial

Update:

```text
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
```

Add:

```text
What is Pareto tradeoff search?
When to use Find best starting design vs Find Pareto tradeoffs
How to load a Pareto candidate into the playground
How to read the Pareto plot
```

## Step 11 — Verification

Backend:

```bash
cd backend
uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
```

Frontend:

```bash
cd frontend
npm run build
```

Manual checks:

- Default flow still works with `Find best starting design`.
- `Find Pareto tradeoffs` requires at least two active objectives or shows a friendly message.
- Pareto candidates appear for balanced fuel-cell objective.
- Loading a Pareto candidate updates sliders, output cards, and predicted curve.
- Pareto plot renders with axis labels and units.
- Existing Design Studio export still works.

## Acceptance criteria

- Single-objective search remains the default/simple path.
- Multi-objective Pareto search is available as a second action.
- Pareto logic is schema-driven and works beyond fuel-cell outputs.
- Non-ML users get a plain-language explanation of what Pareto means.
- Users can load a Pareto candidate into the playground and continue manual exploration.
- Heatmap is explicitly documented as not yet implemented and remains a follow-up feature.

## Heatmap follow-up note

A schema-driven 2D response-surface heatmap already exists in the Batch Visuals flow:

```text
frontend/src/components/ResponseSurfaceHeatmap.tsx
```

It already lets users select:

```text
x variable
y variable
color target output or recommendation score
```

and sweeps two variables while holding the other inputs fixed.

So do **not** build a second, redundant heatmap from scratch as part of the Pareto work. After Pareto search is complete, evaluate whether the existing Batch Visuals heatmap should simply be reused or moved into Design Studio with current slider values as its fixed inputs. If reused, the follow-up should be an integration/refactor plan, not a new heatmap implementation.
