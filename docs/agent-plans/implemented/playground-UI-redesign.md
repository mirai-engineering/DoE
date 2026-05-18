# Task: Redesign ML Model Map into Premium Neural Network Overview
## Goal
Redesign the current **“ML Model Map”** section of the Mirai DoE Engine UI so it feels more premium, elegant, and technically aligned with **surrogate modeling / neural networks**.
The new design should visually resemble the conceptual style of TensorFlow Playground:
- input variables as nodes
- hidden surrogate model layers as connected neural-network nodes
- output KPIs as nodes/cards
- elegant edge connections between them
- premium SaaS styling consistent with the existing Mirai DoE Engine UI
The section should communicate:
> Scientist-controlled experiment inputs are passed into a served surrogate model, which predicts multiple fuel-cell response KPIs and supports candidate search / optimization.
This is a UI/UX improvement only. Do **not** remove existing functionality.
---
## Current Problem
The current section is readable, but it looks like a generic static flowchart:
```text
7 variables → served surrogate model → 4 KPIs + curve

It does not strongly communicate:

* machine learning
* surrogate modeling
* neural network structure
* multi-output prediction
* scientific/engineering intelligence
* premium enterprise product quality

The current large dark rectangle containing the model name feels too heavy and not visually informative.

⸻

Desired Direction

Replace or redesign the current model-map layout into a neural-network-inspired diagram.

Target visual metaphor:

Experiment Inputs        Surrogate Model              Predicted Outputs
7 input nodes       →     hidden layers / graph    →    KPI output nodes

The visual should feel like:

* TensorFlow Playground, but premium and less playful
* scientific visualization
* neural network topology
* calm, elegant enterprise AI dashboard
* consistent with the current Mirai brand

⸻

Design Requirements

Overall Style

Use the existing visual language of the app:

* warm off-white / ivory background
* dark primary panels: near-black navy
* muted sage green section labels
* champagne / muted gold accents for edges or highlighted labels
* large rounded cards
* soft shadows
* spacious layout
* precise typography
* premium enterprise SaaS feel

Avoid:

* bright rainbow colors
* childish node diagrams
* generic AI glowing gradients
* excessive animation
* cluttered graph visuals
* crypto / web3 aesthetics
* copying TensorFlow Playground literally

⸻

Proposed Layout

Create a large rounded card titled:

ML Model Map

Main heading:

From experiment settings to predicted fuel-cell response

Subtitle:

A trained surrogate model maps scientist-controlled inputs to predicted KPIs used by the recommendation engine.

Inside the card, create a horizontal neural architecture diagram with 3 zones:

1. Experiment Inputs → 2. Served Surrogate Model → 3. Predicted Outputs

⸻

Zone 1: Experiment Inputs

Left side.

Display:

1 · EXPERIMENT INPUTS
7 variables
Composition, operating, and aging conditions controlled by the scientist.

Then show 7 small input nodes, labeled directly or via compact tags:

* Pt/C ratio
* I/C ratio
* Ionomer EW
* Operating RH
* Operating voltage
* AST RH
* AST upper potential limit

The nodes should be vertically stacked or gently curved, like the input layer of a neural network.

Each node should be a small circle or pill with a subtle border.

⸻

Zone 2: Served Surrogate Model

Center.

Instead of a huge black rectangle, show a neural-network structure.

Display:

2 · SERVED SURROGATE MODEL
pem_fuel_cell_real_cathode_degradation_mlp_champion

Below that, render a compact neural network:

* 7 input-side nodes
* 2 or 3 hidden layers
* each hidden layer has 4–6 nodes
* output-side nodes connect to KPI outputs
* thin curved or straight SVG lines connect layers
* edges should be subtle champagne / muted gold / low-opacity slate
* nodes should be off-white or champagne on dark background
* one or two paths may be slightly brighter to imply active signal flow

Suggested structure:

[input dots] → [hidden layer 1] → [hidden layer 2] → [latent response] → [outputs]

Include a small status pill:

ONNX Runtime · Champion model · Current

Also include this explanatory line:

Generate result sends the selected inputs through the model. Candidate search samples many inputs, scores the predicted outputs, and ranks the best experiments.

Keep the model name visible, but avoid letting it dominate the visual hierarchy.

⸻

Zone 3: Predicted Outputs

Right side.

Display:

3 · PREDICTED OUTPUTS
4 KPIs + curve
Status: result current

Then show 4 KPI output nodes/cards:

* BoL current density
* EoL current density
* ECSA loss
* Durability score

Optional fifth visual element:

Response curve

Each output should be connected from the final hidden layer.

The outputs should look like small premium cards or output nodes, not just text.

Use direction badges:

* MAXIMIZE for BoL current density
* MAXIMIZE for EoL current density
* MINIMIZE for ECSA loss
* MAXIMIZE for Durability score

⸻

Interaction / Animation

Add subtle animation only if cheap and safe.

Preferred interactions:

* On hover over an input node, highlight the paths from that input toward the model.
* On hover over an output KPI, highlight incoming edges.
* Static SVG is acceptable for MVP.
* Animation should not harm performance.

Avoid:

* complex graph physics
* canvas simulations
* heavy animation libraries
* anything that makes the diagram feel busy

⸻

Implementation Recommendation

Use React + SVG.

Create a dedicated component, for example:

frontend/src/components/ModelMap.tsx

or if the project already has a visualization/components folder, place it there.

Use SVG for:

* node positions
* edges
* curved paths
* subtle active paths

Use regular JSX/CSS/Tailwind for:

* cards
* labels
* badges
* section layout

Avoid heavy graph libraries for this feature. Do not add D3, React Flow, or graph physics unless already installed and clearly necessary.

⸻

Suggested Component API

<ModelMap
  inputs={project.schema.inputs}
  outputs={project.schema.outputs}
  modelName={project.metadata.model_name}
  status="current"
/>

If the current project metadata does not expose the exact model name cleanly, use the existing value currently displayed in the UI.

⸻

Visual Details

Outer Card

Use a large rounded container:

* border radius: 28–36px
* soft border: rgba(15, 23, 42, 0.08)
* background: warm ivory / white
* shadow: soft, large, low opacity
* generous padding
* responsive width

Center Model Panel

Use:

* background: #050918 or similar near-black navy
* text: warm ivory
* label: muted gold
* edges: rgba(216, 201, 155, 0.35)
* active edges: rgba(216, 201, 155, 0.8)
* nodes: warm ivory / champagne
* subtle internal borders

Typography

Use the existing app typography style:

* uppercase tracking labels
* strong headline
* muted explanatory text
* compact metadata pills
* avoid overly small unreadable labels

⸻

Copy Suggestions

Main heading:

From experiment settings to predicted fuel-cell response

Subtitle:

The surrogate model maps controlled experiment variables into predicted KPIs used by the recommendation engine.

Input zone:

Composition, operating, and aging conditions controlled by the scientist.

Model zone:

The served MLP transforms the selected formulation and operating point into a predicted response profile.

Output zone:

Predicted KPIs and response curves become the scoring surface for candidate search.

⸻

Responsive Behavior

Desktop:

* Use a horizontal layout:
    * inputs on the left
    * neural model graph in the center
    * outputs on the right

Tablet / smaller screens:

* Stack the zones vertically if needed.
* Preserve the neural network diagram readability.
* Do not allow text or SVG to overflow.
* Keep labels legible.

⸻

Acceptance Criteria

The task is complete when:

1. The current ML Model Map section is replaced with a premium neural-network-inspired diagram.
2. The diagram clearly shows:
    * experiment inputs
    * served surrogate model
    * predicted KPI outputs
3. The model no longer appears only as a large static black rectangle.
4. The visual resembles a clean, premium version of TensorFlow Playground’s neural-network map.
5. The diagram feels consistent with the current Mirai DoE Engine brand.
6. The layout remains responsive and does not overflow on smaller screens.
7. Existing project metadata and model status are still visible.
8. Existing tabs, prediction flows, recommendation flows, and visualizations are not removed or broken.
9. The frontend builds successfully.
10. The full local stack still runs successfully.

⸻

Validation

Run the frontend build command used by this project, for example:

npm run build

Then run the full local stack:

docker compose up --build

Open the app and verify:

* the ML Model Map renders correctly
* the neural network diagram is legible
* labels are readable
* the model name is visible but not visually overwhelming
* the layout does not overflow
* existing prediction behavior still works
* existing recommendation behavior still works
* existing visualizations still work

⸻

Important Note

Do not copy TensorFlow Playground literally.

Use it only as a conceptual reference for the neural-network topology. The Mirai version should feel darker, calmer, more industrial, more scientific, and more premium.