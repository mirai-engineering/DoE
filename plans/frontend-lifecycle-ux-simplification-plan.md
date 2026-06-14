# Frontend lifecycle UX simplification plan

## Context

The current frontend works functionally, but the user experience feels chaotic because the primary path exposes too much backend/contract detail at once. The intake → metadata approval → preprocessing → training flow is spread across verbose cards, repeated explanations, technical identifiers, and advanced configuration controls that compete with the next required action.

The intended outcome is a more professional product flow: users should always know the current step, the next action, and only the minimum evidence needed to proceed. Technical details should remain available, but secondary/collapsible.

## Agent and skill mapping

- `scout` — intended read-only discovery for the existing frontend flow. Attempted, but failed due to an incorrect working-directory resolution; direct read-only inspection was used instead.
- `reviewer` — use after implementation to review copy reduction, state logic, and regressions before committing.
- `worker` — use only if the UI refactor grows beyond targeted component edits.
- `oracle` — not needed unless we need a higher-level product decision on the lifecycle information architecture.

Relevant skills:
- `frontend-ui-engineering` — simplify component hierarchy, interaction states, and progressive disclosure.
- `scientific-ui-clarity` — preserve scientific meaning while reducing jargon and sentence count.
- `browser-testing-with-devtools` — validate the actual click path visually after implementation.
- `test-driven-development` — keep API/flow behavior covered while changing presentation.
- `git-workflow-and-versioning` — isolate UI changes and avoid mixing unrelated files.

## Approach

Redesign the lifecycle pages around a single guided workflow:

1. **Create project** — upload package and choose project/workspace.
2. **Review metadata** — confirm variable labels and plot setup.
3. **Run preprocessing** — produce canonical model table and EDA evidence.
4. **Approve & train** — approve preprocessing, create request, start training.
5. **Review model quality** — hand off to the existing model-quality page.

Keep the current Mirai visual language, colors, rounded cards, and tab structure, but reduce content density using:

- a compact lifecycle stepper at the top of the intake/review flow;
- one primary CTA per current state;
- short headings and one-line helper text;
- collapsible/secondary technical details for contract requirements, artifact paths, IDs, and advanced training parameters;
- one default **Recommended training** action, with advanced sweep controls hidden behind an “Advanced settings” disclosure;
- a clean metadata summary first, with the full variable table hidden behind an “Edit labels/details” disclosure;
- a smaller **Package requirements** help panel instead of large template/contract education sections;
- generic language, not fuel-cell-specific copy, for the canonical `generic_tabular_doe` path.

## Files to modify

- `frontend/src/components/DataIntakePage.tsx`
  - Reduce upload page copy.
  - Make upload/create-project the single focus.
  - Move package contract details/templates into secondary collapsible/help sections.

- `frontend/src/components/PreprocessingReviewPage.tsx`
  - Reorder sections to match lifecycle order: session summary → metadata → preprocessing → evidence → approval/training.
  - Replace the current four-action button row with state-aware primary action and smaller secondary actions.
  - Hide advanced training configuration by default.
  - Remove fuel-cell-specific headings/copy.

- `frontend/src/components/ProjectHeader.tsx`
  - Reduce header dominance and metadata noise.
  - Keep workspace/project selectors prominent, but move durable-state and metadata-variable details to compact secondary display.

- `frontend/src/components/Tabs.tsx`
  - Shorten tab descriptions and reduce dropdown copy density.

- `frontend/src/components/ui.tsx`
  - Add/reuse small presentational components if useful, such as `LifecycleStepper`, `SectionCard`, `PrimaryActionBar`, or `DisclosurePanel`.

## Reuse

Existing reusable pieces found:

- `StatusPill` in `PreprocessingReviewPage.tsx` — can be reused or moved to shared UI for step/status badges.
- `Metadata` in `ui.tsx` — useful for compact summary cards.
- Existing rounded-card Tailwind style across components — preserve for brand continuity.
- Existing API functions in `frontend/src/lib/api.ts` — no route changes needed.
- Existing `Tabs` grouping — keep the major product areas, but simplify labels/descriptions.

## Steps

- [ ] Define compact UX states for the lifecycle: uploaded, metadata approved, preprocessing complete, preprocessing approved, training requested, training completed.
- [ ] Add a small shared lifecycle stepper/progress component or implement it locally in the lifecycle pages.
- [ ] Simplify `DataIntakePage` so the upload form is the hero and contract/template details are reduced to a compact **Package requirements** panel.
- [ ] Simplify `PreprocessingReviewPage` into a state-driven guided flow with one obvious next action.
- [ ] Replace immediate full metadata editing with a clean summary and an expandable **Edit labels/details** table.
- [ ] Replace visible training hyperparameters with a default **Recommended training** path and an expandable **Advanced settings** section.
- [ ] Move artifact paths, ydata details, and low-level diagnostics behind collapsible sections.
- [ ] Make all lifecycle copy generic and professional; remove fuel-cell-specific phrasing from generic pages.
- [ ] Tighten `ProjectHeader` and `Tabs` copy so navigation does not overwhelm the working area.
- [ ] Preserve all existing API calls and route names.
- [ ] Run frontend build and focused backend tests only if flow-affecting frontend code requires API assumptions.
- [ ] Browser-test the full local flow with the Fraunhofer package: upload → metadata approve → preprocessing → evidence → approve → train → model quality.

## Verification

- `cd frontend && npm run build`
- Local browser/manual path:
  - open app locally;
  - create a fresh project from `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-cell-01.zip`;
  - confirm the page shows a clear next step after upload;
  - approve metadata;
  - run preprocessing;
  - verify preprocessing evidence is concise and readable;
  - approve preprocessing;
  - create/start training;
  - open Model Quality.
- Confirm no public API routes were renamed.
- Confirm canonical variable model remains visible where needed: `x1..xN`, `y1..yM`, with source names available as secondary detail.

## Decisions

- Training should default to one **Recommended training** action; advanced parameters should be hidden under **Advanced settings**.
- Metadata review should show a clean summary first; the full variable table should be available only through **Edit labels/details**.
- Package/template guidance should become a smaller **Package requirements** help panel, not a large main-page section.
