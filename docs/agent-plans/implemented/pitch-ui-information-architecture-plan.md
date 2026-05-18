# Pitch UI Information Architecture Plan

## Context

The product story is now clearer:

> Mirai DoE is a platform that abstracts ML engineering for test engineers and scientists, helping them evaluate, optimize, and justify experiments across technical platforms.

The current MVP does not yet include the future “upload your data and train tailored models” workflow. For pitching, the UI should still make room for that future capability while focusing on today’s working MVP:

- model trust / quality evidence
- ML-guided design and experiment search
- business impact / time saved

Current top-level tabs are too implementation-oriented:

```text
Batch Search
Design Studio
Explore/Optimization Loop
Business Impact
Model Quality
```

The desired pitch-facing root structure should be three high-level product areas:

1. `Tailored ML Model`
2. `ML-Guided Design`
3. `Business Impact`

## Approach

Reorganize the UI navigation into three product-oriented groups while preserving existing working pages and backend behavior.

Recommended pitch-facing grouping:

```text
Tailored ML Model
  - Model Quality
  - Train from your data / Upload data placeholder

ML-Guided Design
  - Design Studio
  - Batch Search
  - Explore & Exploit Tests

Business Impact
  - Business Impact
```

This avoids removing functionality while making the product story easier to understand.

## Files to modify

```text
frontend/src/components/Tabs.tsx
frontend/src/components/ProjectHeader.tsx
frontend/src/types/doe.ts
frontend/src/App.tsx
frontend/src/components/bo/OptimizationLoopPage.tsx
frontend/src/components/BusinessImpactPage.tsx
frontend/src/components/ui.tsx
```

Optional docs update:

```text
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
```

## Reuse

Reuse existing pages:

```text
ModelQualityPage
DesignStudioPage
Batch Search section in App.tsx
OptimizationLoopPage
BusinessImpactPage
```

Reuse existing business-impact summary data:

```text
getBusinessImpactSummary(schema.project_id)
```

Add only lightweight frontend placeholders for future data upload and configurable savings assumptions.

## Steps

### 1. Rename the product shell copy

Update the header from engineering-oriented language:

```text
Surrogate model console
Predict experiment outcomes and recommend the next best candidates.
```

to pitch-friendly language:

```text
ML-guided DoE platform
Abstract ML engineering for test teams: trust tailored models, design better experiments, and quantify saved test effort.
```

### 2. Group the navigation into three root areas

Modify `Tabs.tsx` to render grouped navigation sections instead of one flat list.

Recommended visual:

```text
Tailored ML Model
  [Model Quality] [Upload data — coming soon]

ML-Guided Design
  [Design Studio] [Batch Search] [Explore & Exploit Tests]

Business Impact
  [Business Impact]
```

The upload-data item should be visibly disabled/coming soon, not clickable.

### 3. Keep route/state model simple

Do not introduce a new routing framework.

Keep existing `ActiveTab` values:

```ts
'batch'
'design-studio'
'optimization'
'impact'
'model-quality'
```

Only change labels and grouping.

### 4. Rename Optimization Loop in user-facing copy

Rename tab label from:

```text
Optimization Loop
```

to:

```text
Explore & Exploit Tests
```

Update page header copy from:

```text
Optimization Loop / Sequential BO recommendation
```

to something scientist-friendly:

```text
Explore & Exploit Tests / Choose the next test with measured feedback
```

Explain in copy:

```text
Balance exploring uncertain regions with exploiting designs the model already believes are strong.
```

Keep backend/API names unchanged.

### 5. Keep Batch Search inside ML-Guided Design

Do not remove Batch Search. It still serves a useful batch-screening workflow and complements Design Studio.

Position it after Design Studio because for pitching, Design Studio is the strongest demo.

### 6. Add future upload/train placeholder

Add a disabled nav pill or small card under `Tailored ML Model`:

```text
Upload data & train model — coming soon
```

Tooltip/copy:

```text
Future workflow: upload your test data, validate schema, train tailored surrogate models, then review model quality before design optimization.
```

No backend implementation yet.

### 7. Add lightweight Business Impact assumption placeholders

Business Impact is already good. Add a non-persistent “Customize your savings story” placeholder section with fields such as:

- hours spent per DoE campaign
- fully loaded hourly cost
- campaigns per year
- expected reduction percentage

Calculate simple frontend-only placeholders:

```text
hours saved per campaign = hours per campaign * reduction percentage
cost saved per campaign = hours saved * hourly cost
annualized savings = cost saved per campaign * campaigns per year
```

Label clearly:

```text
Pitch placeholder — not yet connected to saved experiment runs.
```

This previews the future dynamic coupling between design workflows and ROI.

### 8. Update empty-state and tutorial copy

Replace remaining user-facing references to old labels:

```text
Batch Explorer -> Batch Search
Optimization Loop -> Explore & Exploit Tests
```

## Verification

Frontend build:

```bash
cd frontend
npm run build
```

Manual checks:

- Top navigation reads as three product areas.
- `Upload data & train model` is visible as coming soon but does not break navigation.
- Model Quality still works.
- Design Studio still works.
- Batch Search internal tabs still work.
- Explore & Exploit Tests still opens the existing optimization-loop functionality.
- Business Impact shows existing impact evidence plus editable placeholder savings fields.
- No backend changes are required.

## Acceptance criteria

- The UI is easier to pitch as a product platform, not a collection of engineering demos.
- The future upload/train workflow is visible without pretending it is implemented.
- ML-guided design workflows are grouped together.
- Business Impact remains intact and starts hinting at future customer-specific ROI calculations.
