# Task: Polish Existing Dynamic ML Model Map Component
## Goal
Refine the current dynamic **ML Model Map** implementation instead of rebuilding it from scratch.
The current implementation is already close to the desired direction:
- dynamic input list
- dynamic neural-network-style surrogate model panel
- dynamic output list
- premium layout
- schema-driven structure
This task is a cleanup and refinement pass.
Main goals:
1. Remove the cheap-looking numbered prefixes such as `1 · EXPERIMENT INPUTS`, `2 · SERVED SURROGATE MODEL`, `3 · PREDICTED OUTPUTS`.
2. Avoid duplicate implementations or parallel versions of the model map.
3. Preserve the current dynamic component and improve it in place.
4. Make the UI feel more premium, less “step-by-step tutorial”, and more like a polished enterprise scientific dashboard.
---
## Current Issue
The current component visually works, but these labels feel too basic:
```text
1 · EXPERIMENT INPUTS
2 · SERVED SURROGATE MODEL
3 · PREDICTED OUTPUTS

The numbered step labels make the section feel like a generic workflow diagram instead of a premium AI engineering interface.

They should be replaced with cleaner, more elegant section labels.

⸻

Important Implementation Constraint

Do not create a second ModelMap component.

Do not duplicate the current model-map logic.

Do not add a separate static version.

Instead:

* find the currently implemented dynamic model map component
* improve that component directly
* reuse its existing props, helpers, schema parsing, SVG generation, and layout logic
* only extract small subcomponents if it improves readability

The final codebase should have one clear source of truth for this UI.

⸻

Desired Visual Direction

Keep the current structure:

Inputs | Surrogate Model Graph | Outputs

But make the labels feel more refined.

Replace numbered labels with small premium metadata labels such as:

EXPERIMENT SPACE
SERVED SURROGATE
PREDICTED RESPONSE

or:

CONTROLLED VARIABLES
NEURAL SURROGATE MODEL
MODEL OUTPUTS

Recommended final labels:

CONTROLLED VARIABLES
NEURAL SURROGATE
PREDICTED RESPONSE

These are more premium and domain-agnostic.

⸻

Specific UI Changes

1. Remove Numbered Section Prefixes

Remove:

1 ·
2 ·
3 ·

from all section headers.

Do not replace them with other numbers.

The diagram should not feel like a linear onboarding explanation.

⸻

2. Replace Section Labels

Use the following section labels:

Left card:

CONTROLLED VARIABLES

Center panel:

NEURAL SURROGATE

Right card:

PREDICTED RESPONSE

Use the existing uppercase tracking style, but make it slightly more elegant:

* smaller font size
* increased letter spacing
* muted sage for side panels
* muted champagne/gold for center panel
* no numeric prefix

Example style:

text-transform: uppercase;
letter-spacing: 0.18em;
font-size: 0.72rem;
font-weight: 700;

⸻

3. Improve Input Card Copy

Current:

7 variables
Composition, operating, and aging conditions controlled by the scientist.

Keep this idea, but make it more generic and polished.

Recommended:

7 variables
Scientist-controlled formulation, process, and operating conditions.

For the fuel-cell demo this still works well.

Avoid hardcoding too much fuel-cell-specific language unless it comes from project metadata.

⸻

4. Improve Model Panel Copy

Current center title is good, but the model name dominates less now than before.

Keep:

pem_fuel_cell_real_cathode_degradation_mlp_champion

But structure it like this:

NEURAL SURROGATE
pem_fuel_cell_real_cathode_degradation_mlp_champion

Metadata pill:

ONNX Runtime · Champion model · Current

If this pill already exists outside or above the panel, avoid duplicating it inside the panel.

There should only be one metadata/status pill cluster for the model.

⸻

5. Fix Status Pill Clipping

In the screenshot, the small CURRENT pill in the top-right of the dark model panel appears partially clipped.

Fix this.

Options:

* move the pill into a proper header row inside the panel
* increase right padding
* remove the inner CURRENT pill if the top global pill already says CURRENT
* ensure no overflow: hidden clips it unintentionally

Preferred solution:

Use one clean metadata pill row below the model name:

ONNX Runtime · Served model · Current

Then remove any duplicated or clipped small pill from the right edge.

⸻

6. Keep Dynamic Behavior

Do not hardcode:

7 variables
4 KPIs + curve

These should remain dynamic.

Use:

const inputCount = inputs.length;
const outputCount = outputs.length;

Left summary:

{inputCount} variables

Right summary:

{outputCount} outputs

For projects that explicitly define KPI outputs, this can say:

{outputCount} KPIs + curve

But do not assume all future projects are fuel-cell KPI projects.

Preferred generic fallback:

{outputCount} predicted outputs

⸻

7. Avoid Duplicate Metadata

Audit the current implementation for duplicated labels or status indicators.

Avoid having both:

ONNX Runtime · Served Model · Current

at the top of the card and another:

Current

inside the model panel unless it is visually intentional.

Preferred final structure:

Top of full card:

ML MODEL MAP
From experiment settings to predicted response
The surrogate model maps controlled experiment variables into predicted outputs used by the recommendation engine.

Inside center panel:

NEURAL SURROGATE
{modelName}
ONNX Runtime · Champion model · Current

No extra clipped badge.

⸻

Suggested Final Text

Main section eyebrow:

ML MODEL MAP

Heading:

From experiment settings to predicted response

For fuel-cell projects, if the app already injects the domain name, this can become:

From experiment settings to predicted fuel-cell response

Subtitle:

The surrogate model maps controlled experiment variables into predicted outputs used by the recommendation engine.

Left card label:

CONTROLLED VARIABLES

Left card body:

Scientist-controlled formulation, process, and operating conditions.

Center panel label:

NEURAL SURROGATE

Center explanatory copy:

Generate result sends the selected inputs through the model. Candidate search samples many inputs, scores the predicted outputs, and ranks the best experiments.

Right card label:

PREDICTED RESPONSE

Right card body:

Predicted outputs and response curves become the scoring surface for candidate search.

⸻

Code Organization Requirement

Before editing, inspect the current implementation and identify where the new model map was added.

Likely locations may include:

frontend/src/components/ModelMap.tsx
frontend/src/components/ml/ModelMap.tsx
frontend/src/pages/Home.tsx
frontend/src/App.tsx

Only keep one canonical component.

If there are duplicate versions, consolidate into one.

Preferred final structure:

frontend/src/components/ModelMap.tsx

or, if the project uses feature folders:

frontend/src/components/model-map/ModelMap.tsx

Acceptable small subcomponents:

InputVariableList
SurrogateNetworkPanel
OutputResponseList
NeuralNetworkSvg

But only if they live under the same model-map implementation and do not duplicate logic.

⸻

Refactor Rules

Do:

* improve the existing component in place
* preserve schema-driven rendering
* preserve dynamic input/output counts
* preserve SVG neural network generation
* preserve responsive behavior
* clean up labels and copy
* fix clipped badges
* remove duplicated metadata
* keep styling consistent with the current app

Do not:

* create a new static image-based implementation
* create another parallel model-map component
* hardcode the PEM fuel-cell demo values
* remove dynamic schema support
* add heavy graph libraries
* change prediction/recommendation logic
* break existing tabs or flows

⸻

Visual Acceptance Criteria

The task is complete when:

1. The numbered labels 1 ·, 2 ·, and 3 · are removed.
2. The section labels feel premium and scientific:
    * CONTROLLED VARIABLES
    * NEURAL SURROGATE
    * PREDICTED RESPONSE
3. The model status pill is not clipped.
4. There is no duplicated status/metadata clutter.
5. The model map still looks like a premium neural-network diagram.
6. The component still adapts to different numbers of inputs and outputs.
7. There is only one canonical model-map implementation.
8. The UI remains responsive.
9. No existing functionality is removed.

⸻

Functional Acceptance Criteria

Verify with the current PEM Fuel Cell Demo:

* input count is rendered dynamically
* output count is rendered dynamically
* input labels still come from schema
* output labels still come from schema
* objective badges still render correctly when available
* neural graph still renders correctly
* model name still appears
* prediction form still works
* recommendation flow still works
* visualization tab still works

⸻

Validation Commands

Run the frontend build:

npm run build

Then run the full local stack:

docker compose up --build

Open the app and verify the model map visually.

Also search for duplicate components or duplicate labels:

grep -R "EXPERIMENT INPUTS" frontend/src || true
grep -R "SERVED SURROGATE MODEL" frontend/src || true
grep -R "PREDICTED OUTPUTS" frontend/src || true
grep -R "ModelMap" frontend/src || true

There should not be multiple competing implementations of the same model-map UI.

⸻

Final Design Target

The final model map should feel like:

Controlled Variables → Neural Surrogate → Predicted Response

Not like:

Step 1 → Step 2 → Step 3

It should feel less like a tutorial and more like a premium scientific AI control panel.