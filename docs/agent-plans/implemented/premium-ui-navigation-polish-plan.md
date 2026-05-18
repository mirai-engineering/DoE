# Premium UI Navigation Polish Plan

## Context

The new three-root dropdown navigation is conceptually good, but the dropdown menus are currently being visually/clickably obstructed by content below the header. This is a stacking-context problem: the menu is rendered inside the header, while later page sections can paint above it or intercept clicks.

The user also wants the UI to feel premium enough for a high-value product pitch. The current light styling is good, but it needs better hierarchy, more deliberate colors, fewer cluttered long pages, and clearer in-page navigation.

## Approach

Implement a focused polish pass:

1. Fix dropdown stacking and clickability robustly.
2. Make the product navigation look more premium and stable.
3. Add lightweight “On this page” table-of-contents chips for long pages.
4. Slightly refine page colors and section hierarchy without changing backend behavior.

## Files to modify

```text
frontend/src/components/ProjectHeader.tsx
frontend/src/components/Tabs.tsx
frontend/src/App.tsx
frontend/src/components/DesignStudioPage.tsx
frontend/src/components/ModelQualityPage.tsx
frontend/src/components/BusinessImpactPage.tsx
```

Optional:

```text
frontend/src/components/ui.tsx
```

## Reuse

Reuse existing components and state:

```text
Tabs
ProjectHeader
PanelHeader
DesignStudioPage
ModelQualityPage
BusinessImpactPage
```

Do not introduce a new routing framework or backend changes.

## Steps

### 1. Fix dropdown stacking and click behavior

- Make `ProjectHeader` a high z-index stacking layer:

```tsx
relative z-[80] overflow-visible
```

- Make `Tabs` own a higher stacking context:

```tsx
relative z-[90]
```

- Add a fixed transparent click-away overlay while a dropdown is open:

```tsx
<button className="fixed inset-0 z-[85] cursor-default" ... />
```

- Render dropdown menus above the overlay:

```tsx
z-[95]
```

This ensures:

- menus are visible above following page sections
- menu items can be clicked
- clicking outside closes the menu

### 2. Make dropdowns feel more premium

Refine `Tabs.tsx`:

- Slightly wider dropdowns for descriptions
- softer premium background: warm ivory header + white menu body
- subtle active item ring/accent
- replace plain `⌄` with a cleaner text/chevron treatment using CSS rotation
- keep disabled upload item as an intentional roadmap item, not a broken button

### 3. Improve page background depth

In `App.tsx`, subtly refine the global background:

- keep current light styling
- add a darker premium radial/gradient accent behind the header
- preserve readability and avoid darkening the working cards too much

No visual overhaul that would break existing pages.

### 4. Add “On this page” chips to long pages

Add compact in-page navigation chips near top sections.

For `DesignStudioPage`:

```text
On this page: Workspace | Response curve | Tradeoff candidates | Export/compare
```

Add ids to the target sections:

```text
design-workspace
design-response-curve
design-tradeoffs
design-compare
```

For `ModelQualityPage`:

```text
On this page: Trust summary | Split evidence | Error scale | Prediction diagnostics
```

For `BusinessImpactPage`:

```text
On this page: Impact story | ROI assumptions | Evidence | References
```

These chips should be small, premium, and not sticky initially. They help long pages feel organized without adding complexity.

### 5. Slightly elevate hero cards

For the main page hero sections, use a more deliberate premium treatment:

- black/charcoal cards where already working well, e.g. Business Impact
- warm ivory cards for model/design pages
- subtle gold/green accents
- keep clean scientific white plot cards

### 6. Verify

Run:

```bash
cd frontend
npm run build
```

Manual checks:

- Open each root dropdown.
- Dropdown appears above all content.
- All clickable dropdown items work.
- Click outside closes dropdown.
- Disabled upload item remains visible but non-clickable.
- Long pages have useful “On this page” chips.
- Design Studio response curve and controls still work.
- Business Impact placeholder calculator still works.

## Acceptance criteria

- Dropdowns are no longer hidden or blocked by page content.
- Navigation reads as a premium product IA, not developer tabs.
- Long pages are easier to scan during a pitch.
- Styling remains professional, light, and scientific, with selective premium dark/gold/green accents.
