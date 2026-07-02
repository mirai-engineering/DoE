# App-Wide Product UI Restyle Plan

## Context
- The sidebar and Data Intake restyle improved the app feel by reducing nested cards, heavy borders, glows, and over-explained/generated UI copy.
- Requested next scope: create a plan to update the rest of the authenticated web app in the same direction.
- Target product feel: quiet, technical, trustworthy engineering software with selective Mirai personality — closer to Linear / Vercel / Ramp / Figma engineering tools than a generic AI dashboard.
- Out of scope:
  - Landing page visual redesign.
  - Functional/backend changes.
  - Reworking the already-updated sidebar and Data Intake page except for small consistency adjustments caused by shared primitives.

## Current findings
- `frontend/src/components/ProjectHeader.tsx` is still a large rounded dashboard card with nested metadata cards; it should become a compact app bar/header.
- `frontend/src/components/ui.tsx` still contains card-heavy shared primitives (`SectionCard`, `Metadata`, `PanelHeader`, `EmptyRecommendationsState`) and all-caps label patterns used across the app.
- `frontend/src/components/PreprocessingReviewPage.tsx` is the most card-dense page: many `SectionCard`s, nested `rounded-2xl` blocks, uppercase labels, and action panels.
- `frontend/src/components/ModelQualityPage.tsx` already contains the exact issues from the original feedback: summary cards, large rounded sections, nested metric cards, and verbose explanatory copy.
- `frontend/src/components/DesignStudioPage.tsx` and `frontend/src/components/bo/OptimizationLoopPage.tsx` are large workflows with many rounded white/dark panels, pill labels, and nested controls.
- Batch/search pages (`PredictPanel.tsx`, `RecommendPanel.tsx`, `RecommendationsPage.tsx`, `RecommendationsTable.tsx`, `KpiComparisonChart.tsx`, `ParallelCoordinatesChart.tsx`, `ResponseSurfaceHeatmap.tsx`, `VisualizationsPage.tsx`) use large card shells around tables/charts that should be flattened so data becomes the visual center.
- `frontend/src/components/BusinessImpactPage.tsx` uses large ROI/story cards; it should become a concise decision page with tables/sections and fewer boxed metrics.
- `frontend/src/components/DataScientistPage.tsx` is the one page where purple/personality is appropriate, but it still needs less chrome and fewer sci-fi labels.

## Approach
- Do the redesign in layers to avoid visual regressions:
  1. Establish shared app UI primitives and naming conventions.
  2. Convert the global project header into a compact app bar.
  3. Restyle high-impact pages one workflow at a time.
  4. Run visual and build verification after each phase.
- Keep all current behavior, API calls, state, routing, and data transformations unchanged.
- Prefer flat sections separated by whitespace and subtle dividers over cards.
- Reserve cards for independent artifacts/actions: training run, model artifact, recommendation, agent conversation, confirmation/action panel.
- Reduce radius system across the app:
  - 6px controls/buttons.
  - 8px small panels/tables.
  - 12px major surfaces.
  - Avoid `rounded-2xl`, `rounded-3xl`, and `rounded-[2rem]` for operational UI unless there is a strong reason.
- Reduce uppercase/tracked labels in operational UI. Keep occasional small labels only where they aid scanning.
- Apply semantic color ownership:
  - Blue: primary actions, selected states, active model/selection.
  - Purple: AI/agent surfaces only.
  - Green/cyan: validated/ready/passed.
  - Amber: provisional/needs review.
  - Red: failed/blocked.
  - Muted slate: secondary metadata.
- Prioritize tables, charts, split summaries, diagnostics, and model/results evidence as the visual center.

## Files to modify

### Shared shell and primitives
- `frontend/src/components/ProjectHeader.tsx`
- `frontend/src/components/ui.tsx`
- `frontend/src/index.css` if reusable CSS utilities are cleaner than repeated Tailwind class strings.
- `frontend/src/App.tsx` only if content spacing or loading/error shells need to align with the new flatter system.

### Preprocessing and lifecycle
- `frontend/src/components/PreprocessingReviewPage.tsx`

### Model quality
- `frontend/src/components/ModelQualityPage.tsx`

### Design and optimization workflows
- `frontend/src/components/DesignStudioPage.tsx`
- `frontend/src/components/ModelMap.tsx`
- `frontend/src/components/bo/OptimizationLoopPage.tsx`

### Batch search and recommendation evidence
- `frontend/src/components/PredictPanel.tsx`
- `frontend/src/components/RecommendPanel.tsx`
- `frontend/src/components/RecommendationsPage.tsx`
- `frontend/src/components/RecommendationsTable.tsx`
- `frontend/src/components/KpiComparisonChart.tsx`
- `frontend/src/components/ParallelCoordinatesChart.tsx`
- `frontend/src/components/ResponseSurfaceHeatmap.tsx`
- `frontend/src/components/VisualizationsPage.tsx`

### Impact and agent surface
- `frontend/src/components/BusinessImpactPage.tsx`
- `frontend/src/components/DataScientistPage.tsx`

## Reuse
- Reuse the quieter `LifecycleStepper` and `DisclosurePanel` direction already implemented in `frontend/src/components/ui.tsx`.
- Reuse `PanelHeader` and `Metadata` conceptually, but restyle them into flatter `PageHeader` / inline metadata patterns rather than boxed cards.
- Reuse existing tables/charts and data preparation code; only adjust surrounding chrome, spacing, row emphasis, and semantic highlighting.
- Reuse existing page tab/state structures in `App.tsx`, `DesignStudioPage.tsx`, `ModelQualityPage.tsx`, and `OptimizationLoopPage.tsx`.
- Reuse the Data Scientist page’s purple ownership for agent activity, but remove purple/glow language from non-agent pages.

## Recommended implementation steps

### Phase 1 — Shared visual system
- [ ] Add or refactor shared primitives in `ui.tsx` for:
  - flat page headers,
  - section dividers,
  - quiet inline metadata,
  - compact status pills,
  - restrained major surfaces,
  - table/chart section wrappers.
- [ ] Keep backwards-compatible props where possible to reduce risky rewrites.
- [ ] Replace `SectionCard` default styling with a quieter 12px max-radius surface, or add a `flat`/`section` variant and migrate pages intentionally.
- [ ] Restyle `Metadata` so it can render inline metadata instead of always becoming a bordered mini-card.
- [ ] Standardize button/control radii to `rounded-md` or 6px-equivalent classes.

### Phase 2 — Compact app header
- [ ] Convert `ProjectHeader.tsx` from a large dashboard card into a compact app bar.
- [ ] Keep workspace and project selectors, but reduce their visual weight.
- [ ] Convert inputs/outputs/model-quality status from metadata cards into one inline metadata row, e.g. `7 inputs · 4 outputs · Model ready`.
- [ ] Keep backend/artifact status checks unchanged.
- [ ] Adjust `App.tsx` vertical spacing if needed so content starts closer to the top.

### Phase 3 — Model Quality page
- [ ] Restructure `ModelQualityPage.tsx` around the previously suggested model-validation direction:
  - concise page title and metadata row,
  - compact overview/performance summary,
  - candidate model table as the center,
  - diagnostics and artifacts as flatter sections.
- [ ] Remove or flatten redundant summary cards such as competing active/best/approval/serving blocks.
- [ ] Highlight champion/challenger rows using a subtle blue left marker/tint rather than separate giant cards.
- [ ] Right-align numeric metric columns and simplify table chrome.
- [ ] Shorten AI-generated copy; move detailed scientific explanations into details/help text.

### Phase 4 — Preprocessing Review page
- [ ] Break `PreprocessingReviewPage.tsx` into flatter lifecycle sections: session, metadata, evidence, ML preprocessing, training, admin/debug.
- [ ] Replace repeated metric cards with inline metadata rows or compact tables.
- [ ] Make action areas visually distinct but not oversized; cards only for approval/training actions that have lifecycle/status.
- [ ] Keep the agent-like ML preprocessing chat purple/agent-aware only where it represents AI activity.
- [ ] Reduce rounded-2xl nested blocks and uppercase labels throughout.

### Phase 5 — Design Studio and Model Map
- [ ] Restyle `DesignStudioPage.tsx` as a working surface with a compact workflow selector and flat sections.
- [ ] Reduce cards around configuration controls; group controls with dividers and whitespace.
- [ ] Make charts/model map/results the primary visual focus.
- [ ] Restyle `ModelMap.tsx` nodes and surrounding shell with smaller radii and subtler borders.
- [ ] Preserve all existing prediction, visualization, overlay, and workflow behavior.

### Phase 6 — Explore & Exploit / Optimization loop
- [ ] Restyle `OptimizationLoopPage.tsx` using the same flat working-surface pattern.
- [ ] Make recommendations, candidates, acquisition decisions, and optimization loop evidence central.
- [ ] Reduce decorative pills and uppercase labels.
- [ ] Keep amber/blue status semantics for review vs active selection.

### Phase 7 — Batch search, recommendations, and visualizations
- [ ] Restyle `PredictPanel.tsx` and `RecommendPanel.tsx` from large rounded cards into compact configuration/action sections.
- [ ] Restyle `RecommendationsPage.tsx` summary metadata as inline facts, not five metadata cards.
- [ ] Restyle `RecommendationsTable.tsx` so the table feels native to the product: subtle row dividers, right-aligned numbers, selected/top rows with restrained emphasis.
- [ ] Remove oversized card shells around `KpiComparisonChart`, `ParallelCoordinatesChart`, and `ResponseSurfaceHeatmap`; use headings, dividers, and direct chart placement.

### Phase 8 — Business Impact page
- [ ] Convert ROI summary cards into a concise decision page with a clear top-line statement and compact evidence sections.
- [ ] Use semantic green/cyan sparingly for validated savings/impact, amber for assumptions needing review.
- [ ] Replace long marketing-like explanations with concise labels and optional details.

### Phase 9 — Data Scientist page
- [ ] Keep purple as the AI/agent-owned accent.
- [ ] Reduce sidebar badges/cards and dense monospace uppercase labels.
- [ ] Make the chat panel calmer: less glow/shadow, cleaner message bubbles, compact tool activity.
- [ ] Preserve scoped/read-only/tool-citation affordances.

### Phase 10 — Cleanup and consistency pass
- [ ] Search for remaining excessive operational UI patterns:
  - `rounded-[2rem]`, `rounded-3xl`, excessive `rounded-2xl`,
  - repeated `uppercase tracking-[...]`,
  - nested `border ... bg ... p-4` containers,
  - heavy `shadow-xl`, `shadow-2xl`, glow shadows.
- [ ] Remove or justify each remaining instance.
- [ ] Confirm landing page remains visually distinct and unaffected.
- [ ] Confirm Data Intake/sidebar remain consistent with the broader app.

## Verification
- [ ] Run `cd frontend && npm run lint` after each major phase.
- [ ] Run `cd frontend && npm run build` before final review.
- [ ] Manually check these routes/tabs in expanded and collapsed sidebar modes:
  - Data Intake,
  - Preprocessing,
  - Model Quality,
  - Data Scientist,
  - Design Studio,
  - Batch Search configure/results/visuals,
  - Explore & Exploit,
  - Business Impact.
- [ ] Check loading, empty, error, warning, blocked, ready, and completed states where each page supports them.
- [ ] Check tables/charts at desktop and tablet widths for overflow and readability.
- [ ] Confirm keyboard focus remains visible on buttons, links, inputs, selects, textareas, tabs, details/summary controls, and sidebar controls.
- [ ] Confirm color semantics: blue selection/primary, purple only agent, amber review, red error, muted slate metadata.
- [ ] Compare before/after screenshots for card reduction, visual hierarchy, density, and data prominence.

## Risk management
- The biggest files (`DesignStudioPage.tsx`, `OptimizationLoopPage.tsx`, `PreprocessingReviewPage.tsx`, `ModelQualityPage.tsx`) should be changed in separate commits/phases.
- Shared primitive changes can affect many pages; migrate intentionally and verify after each page group.
- Do not combine visual refactors with logic/API changes.
- If time is constrained, prioritize in this order:
  1. `ProjectHeader.tsx`,
  2. `ModelQualityPage.tsx`,
  3. `PreprocessingReviewPage.tsx`,
  4. `DesignStudioPage.tsx`,
  5. remaining recommendation/impact/agent pages.
