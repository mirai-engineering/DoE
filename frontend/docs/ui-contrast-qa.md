# Mirai UI Contrast and Chart QA Checklist

Use this checklist before accepting changes to the authenticated scientific app.

## Chart readability
- Axis titles, tick labels, legends, and annotations are readable at 1440px and 1024px widths.
- Model Quality parity and residual plots show clear measured/predicted labels and reference lines.
- Design Studio response curves keep labels, overlays, annotations, and legends readable.
- BO/optimization charts keep legends visible without clipping.
- Data-series colors are used for data; UI text colors come from shared theme defaults.

## Dark surface text
- Meaningful secondary text is not below accessible contrast.
- Labels, descriptions, values, warnings, and empty states are readable on glass/premium surfaces.
- Metadata tiles are visually lighter but still scannable.

## Controls and focus
- Inputs, selects, buttons, checkboxes, and tabs have obvious interactive states.
- Keyboard focus rings are visible on dark surfaces.
- Disabled states are distinguishable without becoming unreadable.

## Required screenshot pages
- Landing page at 1440px as the visual benchmark.
- Authenticated app shell/project header at 1440px and 1024px.
- Model Quality: parity plot and residual diagnostic.
- Design Studio: response plot workflow.
- Design Studio optimize/Pareto view, when data is available.
- Explore & Exploit / BO page with at least one chart, when accessible.

## Build command
```bash
cd frontend && npm run build
```

No contrast script was added in this pass; verification is token review plus browser screenshots.
