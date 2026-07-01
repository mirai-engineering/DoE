# Implementation Plan: UI Contrast and Professional Polish

## Overview
Mirai's authenticated app uses a dark shell, but many chart layouts and UI fragments still carry light-theme assumptions or ad-hoc colors. The screenshot shows Plotly axis labels, ticks, and legends with insufficient contrast against the surrounding dark surface. The fix should be systemic: establish accessible semantic tokens, centralize Plotly chart theming, migrate chart-heavy pages to the shared theme, and verify in-browser with screenshots and contrast checks.

## Evidence from screenshot and repo discovery
- Screenshot symptom: chart axis titles, tick labels, and legend are low-contrast on dark background; chart labels appear visually subordinate to the plot despite being essential scientific context.
- `frontend/src/index.css` currently uses broad dark-shell CSS overrides for many light classes, which helps but is fragile and can create inconsistent contrast.
- Plotly layouts are duplicated and hardcoded in:
  - `frontend/src/components/ModelQualityPage.tsx`
  - `frontend/src/components/DesignStudioPage.tsx`
  - `frontend/src/components/KpiComparisonChart.tsx`
  - `frontend/src/components/ParallelCoordinatesChart.tsx`
  - `frontend/src/components/ResponseSurfaceHeatmap.tsx`
  - `frontend/src/components/bo/OptimizationLoopPage.tsx`
- Current chart layouts often use light-theme text colors such as `#334155`, `#64748b`, or `#0f172a`; these are fine on white plot backgrounds but fail when legends/titles sit outside the white plot area on dark cards.
- Frontend stack: React + Vite + Tailwind + Plotly (`react-plotly.js`, `plotly.js-dist-min`).

## Research summary
External accessibility/design guidance points to these standards:
- WCAG 2.2 / MDN: normal text should meet at least 4.5:1 contrast; large text at least 3:1.
- W3C non-text contrast: meaningful visual boundaries, graphical objects, focus states, and controls should generally meet at least 3:1.
- Data visualization guidance from Tableau/Harvard-style accessibility resources: charts need readable titles, axes, legends, labels, and non-color-only distinctions.
- Professional dark-theme systems such as Atlassian/Material-style guidance favor semantic tokens and restrained palettes over per-component hex codes.

## Agent and skill mapping

### Agent-to-task map
| Plan area | Primary agent | Supporting agent | Required skills | Purpose |
| --- | --- | --- | --- | --- |
| Repo/page discovery before implementation | `scout` | none | `frontend-ui-engineering`, `scientific-ui-clarity` | Inventory chart layouts, bulky cards, duplicated colors, and page-specific risk without editing code. |
| Final implementation plan review | `planner` | none | `planning-and-task-breakdown`, `source-driven-development` | Check that tasks are sequenced, scoped, and traceable to evidence/research. |
| Chart accessibility implementation review | `reviewer` | none | `scientific-ui-clarity`, `frontend-ui-engineering`, `code-review-and-quality` | Confirm labels, units, legends, and visual encodings are accessible and scientifically readable. |
| Runtime UI verification | main assistant with DevTools | optionally `reviewer` | `browser-testing-with-devtools`, `frontend-ui-engineering` | Capture screenshots, inspect computed colors, confirm console cleanliness and responsiveness. |
| Final diff review | `reviewer` | optionally `scout` | `code-review-and-quality`, `frontend-ui-engineering` | Catch over-broad CSS overrides, accidental redesign, dead helper code, or unverified hardcoded colors. |

### Skill-to-phase map
| Skill | Use in this plan |
| --- | --- |
| `scientific-ui-clarity` | Chart labels, axis/title hierarchy, units, legends, residual/parity plot readability, and avoiding color-only scientific meaning. |
| `frontend-ui-engineering` | Token architecture, component density, app-shell polish, responsive behavior, reusable chart theme design. |
| `browser-testing-with-devtools` | Runtime screenshots, computed contrast checks, viewport testing, console/network sanity checks. |
| `planning-and-task-breakdown` | Keep the contrast and density work split into reviewable phases/checkpoints. |
| `source-driven-development` | Ground contrast requirements in WCAG/Plotly docs rather than subjective taste. |
| `code-review-and-quality` | Verify maintainability, limited scope, no unnecessary dependencies, and no brittle CSS hacks. |

### Concrete activation sequence
1. Use `scout` once more before implementation to produce a focused inventory of chart and density hotspots in authenticated app pages only.
2. Implement Tasks 1-2 using `frontend-ui-engineering` and `source-driven-development` guidance.
3. Implement chart migrations using `scientific-ui-clarity`.
4. Use `browser-testing-with-devtools` after Model Quality is fixed and again after app-wide migration.
5. Use `reviewer` for final accessibility/maintainability review before commit.

## Architecture decisions
1. **Centralize chart theming instead of patching each plot ad hoc.**
   - Create a shared Plotly theme helper in `frontend/src/lib/plotlyTheme.ts` or adjacent to `frontend/src/lib/plotly.ts`.
   - Provide presets for dark-card/light-plot charts and transparent dark charts.

2. **Use semantic UI tokens before more one-off hex values.**
   - Add CSS variables in `frontend/src/index.css` for app surfaces, borders, text, muted text, chart text, grid lines, accent colors, and focus rings.
   - Keep existing Mirai dark branding, but make contrast measurable and repeatable.

3. **Keep scientific plots readable first, beautiful second.**
   - Axis titles, tick labels, legends, and annotations must meet contrast expectations.
   - Avoid making gridlines too strong; they should support reading without overpowering points.

4. **Push the authenticated app toward a premium, landing-page-adjacent feel while preserving readability and usability.**
   - The landing page feels better because it uses slimmer type hierarchy, softer borders, glass/gradient depth, tighter cards, smaller metadata text, and more spacious section-level rhythm.
   - The app feels chunky because many authenticated components use heavy dark blocks (`#0B1220`), thick/bright borders, large `p-6` cards, `shadow-xl`, repeated rounded boxes, and dense nested panels.
   - Direction: premium operational cockpit, not marketing page. Use glassy/elevated surfaces, subtle gradients, softer shadows, refined spacing, and clearer hierarchy, but keep controls obvious, labels readable, and workflows efficient.
   - Readability and usability outrank decoration: no low-contrast glass, no tiny labels for required controls, no hidden affordances, no layout shifts that slow scientific work.

5. **Prefer modest, high-impact changes over a full redesign.**
   - Preserve current layout structure and branding.
   - Focus initially on chart readability, card density, borders, secondary text, form controls, navigation weight, and buttons.

## Target contrast rules
- Body/normal text on dark surfaces: >= 4.5:1.
- Muted/help text on dark surfaces: still target >= 4.5:1 when it carries meaning; do not use barely visible gray for labels.
- Chart axis titles, tick labels, legends: >= 4.5:1 against their actual background.
- Gridlines, borders, focus rings, chart reference lines: >= 3:1 when they convey meaning; decorative lines may be softer but must not be mistaken for data.
- Color-coded data series: do not rely on color alone where interpretation matters; use legends, labels, symbols, or line styles.

## Task list

### Phase 1: Audit and token foundation

#### Task 1: Add semantic color token inventory
**Description:** Define a small set of app and chart color tokens in `frontend/src/index.css`, without changing layout structure.

**Acceptance criteria:**
- [ ] Tokens exist for `--mirai-bg`, `--mirai-surface`, `--mirai-surface-elevated`, `--mirai-border`, `--mirai-text`, `--mirai-text-muted`, `--mirai-text-subtle`, `--mirai-accent`, `--mirai-chart-axis`, `--mirai-chart-grid`, `--mirai-chart-reference`.
- [ ] Token values preserve the current dark Mirai brand.
- [ ] No broad visual redesign is introduced in this task.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] Manual inspect CSS variables in DevTools.

**Files likely touched:**
- `frontend/src/index.css`

**Dependencies:** None

**Estimated scope:** Small

#### Task 2: Create shared Plotly theme helper
**Description:** Build a reusable helper for Plotly layouts so axis labels, tick labels, legends, annotations, gridlines, and reference lines have consistent contrast.

**Acceptance criteria:**
- [ ] Shared helper exports a base layout for dark-card/light-plot charts.
- [ ] Helper sets `font.color`, `xaxis.tickfont`, `yaxis.tickfont`, `xaxis.title.font`, `yaxis.title.font`, `legend.font`, `gridcolor`, and `zerolinecolor` explicitly.
- [ ] Helper supports overrides without losing required contrast defaults.
- [ ] Existing `plotConfig` can remain, but new chart layout defaults are shared.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] TypeScript compiles without `any` sprawl beyond current Plotly casting conventions.

**Files likely touched:**
- `frontend/src/lib/plotlyTheme.ts`
- optionally `frontend/src/lib/plotly.ts`

**Dependencies:** Task 1

**Estimated scope:** Medium

### Phase 2: Fix chart-heavy pages

#### Task 3: Migrate Model Quality charts
**Description:** Apply the shared Plotly theme to Model Quality charts, including the parity plot and residual diagnostic shown in the screenshot.

**Acceptance criteria:**
- [ ] Parity plot axis labels, ticks, and legend are clearly readable.
- [ ] Residual diagnostic axis labels and reference line remain readable.
- [ ] White plot area still preserves data readability.
- [ ] Titles/annotations such as polarization context use accessible colors.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] Browser screenshot of Model Quality before/after.
- [ ] Console has no errors.

**Files likely touched:**
- `frontend/src/components/ModelQualityPage.tsx`

**Dependencies:** Tasks 1-2

**Estimated scope:** Medium

#### Task 4: Migrate Design Studio charts
**Description:** Apply the same Plotly chart theme to response curves and Pareto plots in Design Studio.

**Acceptance criteria:**
- [ ] Response curve labels, legends, and overlays are readable on dark cards.
- [ ] Pareto chart axes and legend are readable.
- [ ] Existing plot annotation modes and overlays remain functional.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] Browser check Design Studio plot and optimize workflows.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`

**Dependencies:** Tasks 1-2

**Estimated scope:** Medium

#### Task 5: Migrate reusable chart components
**Description:** Update reusable chart components so future pages inherit the same readable chart styling.

**Acceptance criteria:**
- [ ] `KpiComparisonChart`, `ParallelCoordinatesChart`, `ResponseSurfaceHeatmap`, and BO charts use shared theme defaults.
- [ ] Transparent dark charts do not use dark axis text.
- [ ] Legends are visible and placed without clipping.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] Browser check pages/components where these charts render.

**Files likely touched:**
- `frontend/src/components/KpiComparisonChart.tsx`
- `frontend/src/components/ParallelCoordinatesChart.tsx`
- `frontend/src/components/ResponseSurfaceHeatmap.tsx`
- `frontend/src/components/bo/OptimizationLoopPage.tsx`

**Dependencies:** Tasks 1-2

**Estimated scope:** Medium

### Phase 3: Broader professional polish and density audit

#### Task 6: Add premium authenticated-app density and surface primitives
**Description:** Reduce the chunky feel by creating more refined component primitives for authenticated app cards, panels, metadata, inputs, and buttons. Use the landing page as the visual reference for premium polish, but keep the app optimized for daily scientific operation.

**Acceptance criteria:**
- [ ] `SectionCard` uses a premium surface treatment or exposes a variant such as `variant="glass|solid|subtle"` and `density="compact|normal"`.
- [ ] Primary workflow containers feel elevated and polished through subtle gradients/glass/borders, not heavy black shadows.
- [ ] Nested panels use softer borders, less accumulated padding, and clearer section grouping.
- [ ] Metadata tiles use smaller vertical padding and lighter visual weight while staying legible.
- [ ] Buttons and form fields keep touch/accessibility targets but reduce bulky shadows and repeated boxed containers.
- [ ] Project header and sidebar feel slimmer, more premium, and easier to scan.
- [ ] Every premium/glass treatment still passes readability checks for labels, descriptions, values, and control states.

**Recommended design moves:**
- Replace repeated `shadow-xl shadow-black/25` with subtler depth: soft border highlights, very low-opacity glows, and restrained backdrop blur where supported.
- Use a surface hierarchy: app background → elevated nav/header → workflow card → nested control group, instead of every child being the same heavy block.
- Reduce default section padding from `p-6` to `p-4`/`p-5` for operational content, while allowing generous breathing room around major workflows.
- Use `rounded-xl`/`rounded-2xl` intentionally for premium cards, but avoid excessive nested roundness.
- Reduce nested border contrast; use separators, spacing, and headings instead of boxing every child.
- Keep app headings more refined than oversized: strong hierarchy, but not landing-page hero scale.
- Keep forms unmistakably interactive: visible input backgrounds, focus rings, labels, disabled states, and error/warning states.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] Browser compare authenticated app vs landing page at 1440px: app should feel lighter while still utilitarian.
- [ ] Check 1024px viewport to ensure compact density does not crowd controls.

**Files likely touched:**
- `frontend/src/components/ui.tsx`
- `frontend/src/App.tsx`
- `frontend/src/components/ProjectHeader.tsx`
- `frontend/src/components/Tabs.tsx`
- targeted page components only where bulky one-off classes bypass shared primitives

**Dependencies:** Task 1

**Estimated scope:** Medium

#### Task 7: Audit global text and border overrides
**Description:** Replace fragile or insufficient dark-shell overrides with semantic classes/tokens where the biggest readability issues occur.

**Acceptance criteria:**
- [ ] Secondary text that carries meaning is not below accessible contrast.
- [ ] Borders and dividers are visible enough to define cards/forms without visual clutter.
- [ ] Focus states remain obvious on dark surfaces.
- [ ] No public API or backend behavior changes.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] Keyboard tab through main app sections and confirm visible focus.

**Files likely touched:**
- `frontend/src/index.css`
- `frontend/src/components/ui.tsx`
- targeted page components only if necessary

**Dependencies:** Tasks 1 and 6

**Estimated scope:** Medium

#### Task 8: Add visual QA checklist and optional contrast script
**Description:** Document the standard so future chart/UI work does not regress. If lightweight enough, add a no-dependency script or test helper for known token contrast ratios.

**Acceptance criteria:**
- [ ] A checklist exists for chart labels, legends, focus states, and dark-surface text.
- [ ] If a script is added, it checks token pair contrast ratios without introducing unnecessary dependencies.
- [ ] Checklist names the exact pages that must be screenshot-verified.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] If script added: run exact script command and document result.

**Files likely touched:**
- `docs/ui-contrast-qa.md` or `frontend/docs/ui-contrast-qa.md`
- optionally `frontend/scripts/check-contrast.*`
- optionally `frontend/package.json`

**Dependencies:** Tasks 1-7

**Estimated scope:** Small to Medium

### Phase 4: Browser verification and review

#### Task 9: Runtime browser verification
**Description:** Use Chrome DevTools to validate the app visually in real runtime conditions, including the screenshot scenario.

**Acceptance criteria:**
- [ ] Screenshot captured for Model Quality parity plot and residual diagnostic.
- [ ] Screenshot captured for Design Studio response plot.
- [ ] Screenshot captured for at least one BO/optimization chart if accessible.
- [ ] Console has no new warnings/errors.
- [ ] Page remains readable at 1024px and 1440px widths.

**Verification:**
- [ ] Browser screenshots saved or summarized.
- [ ] `cd frontend && npm run build`

**Files likely touched:** None unless issues are found.

**Dependencies:** Tasks 3-7

**Estimated scope:** Small

#### Task 10: Review and final cleanup
**Description:** Run a focused review for accidental visual churn, hardcoded colors left behind, and scientific clarity.

**Acceptance criteria:**
- [ ] Reviewer confirms chart labels/legends are readable.
- [ ] No large unrelated redesigns are included.
- [ ] Remaining hardcoded colors are either intentional data-series colors or documented exceptions.

**Verification:**
- [ ] `cd frontend && npm run build`
- [ ] Optional: `cd frontend && npm run lint` if current lint baseline is expected to pass.

**Dependencies:** Tasks 1-9

**Estimated scope:** Small

## Checkpoints

### Checkpoint A: Foundation approved
After Tasks 1-2:
- [ ] Token palette reviewed.
- [ ] Shared Plotly helper reviewed.
- [ ] Build passes.

### Checkpoint B: Screenshot issue fixed
After Task 3:
- [ ] The exact Model Quality screenshot issue is resolved.
- [ ] Axis titles/ticks/legends are readable.
- [ ] No plot data regression.

### Checkpoint C: App-wide chart consistency
After Tasks 4-5:
- [ ] Major charts use consistent theming.
- [ ] No page has obvious dark-on-dark or low-contrast chart labels.

### Checkpoint D: Professional polish ready for review
After Tasks 6-10:
- [ ] Browser screenshots confirm contrast and density improvement.
- [ ] Authenticated app feels premium and visually closer to the landing page's refinement without sacrificing scientific readability, workflow speed, or control clarity.
- [ ] Contrast checklist exists.
- [ ] Final diff is scoped and reviewable.

## Risks and mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Plotly labels may render partly inside and partly outside plot area | Medium | Explicitly style axis titles, ticks, legends, and margins; verify with screenshots. |
| Broad CSS overrides may accidentally change Clerk/auth or landing page styling | Medium | Keep changes scoped to `.mirai-auth-shell` and chart helpers; inspect affected pages. |
| Premium glass/gradient styling could reduce readability | High | Treat readability as non-negotiable: explicit text tokens, contrast checks, and browser screenshots before accepting visual polish. |
| White plot backgrounds may clash with dark premium cards | Low/Medium | Use subtle card framing and explicit chart typography; do not force all plots dark unless data readability is verified. |
| Too many one-off hex colors remain | Medium | Centralize chart and surface tokens first, then migrate high-impact areas. |
| Data-series colors may fail colorblind distinction | Medium | Preserve current data meaning but add symbols/line styles where needed in later pass. |

## Open questions
- Should Mirai charts stay as white plot panels inside dark premium cards, or should we move toward full dark Plotly plots? Recommendation: keep white plot panels for now because they maximize dense data readability and require the smallest safe change; revisit dark plots only after contrast and data-series testing.
- Should this include the public landing page? Recommendation: no, the landing page is already the visual benchmark; keep this pass focused on authenticated scientific app surfaces.
- Should we add an automated accessibility tool such as axe? Recommendation: not in the first pass unless approved, because it adds dependency/config scope. Start with token checks + DevTools screenshots.
- How far should premium styling go? Decision: push toward premium operational-cockpit quality, but readability and usability remain the goal and override decorative treatments.

## Proposed implementation branch/commit strategy
1. `fix: add accessible UI and chart tokens`
2. `fix: centralize Plotly chart contrast theme`
3. `fix: improve model quality chart readability`
4. `fix: apply chart contrast theme across app`
5. `style: reduce authenticated app visual weight`
6. `docs: add UI contrast QA checklist`

## Exact local commands
```bash
cd frontend
npm run build
npm run lint
```

If backend remains untouched, no backend pytest is required for this UI-only work.
