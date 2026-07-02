# Sidebar and Data Intake Restyle Plan

## Context
- Feedback: the app UI feels too card-heavy and generated compared with the more restrained landing page.
- Requested scope: change **only** the sidebar navigation and the **Data Intake** page/tab to test whether a flatter, calmer product UI improves perceived quality.
- Current implementation findings:
  - Sidebar lives in `frontend/src/components/Tabs.tsx` and uses a rounded bordered shell plus bordered mini-card buttons, subtitles, badges, and per-item descriptions.
  - Data Intake lives in `frontend/src/components/DataIntakePage.tsx` and uses nested surfaces: `LifecycleStepper`, `SectionCard`, dashed upload panel, radio option cards, requirements card, disclosure card, status cards.
  - Shared components involved: `LifecycleStepper`, `SectionCard`, and `DisclosurePanel` in `frontend/src/components/ui.tsx`.
  - Global dark app overrides in `frontend/src/index.css` force light utility classes into dark equivalents.

## Approach
- Keep the existing functionality, data flow, state, API calls, tab routing, and user-controlled sidebar collapse behavior unchanged.
- Limit the experiment’s intended visual impact to the sidebar and Data Intake page/tab; shared component changes are allowed only when they support these areas and should be checked for side effects.
- Make the sidebar read as navigation, not a stack of cards: text-first groups, subtle inactive items, one active state with a 2px blue left accent.
- Rework Data Intake into the layout that best improves readability and avoids an AI-generated dashboard feel: a flatter operational page with a concise header, compact workflow status, a clear primary upload/action area, and quieter secondary requirements/template information.
- Prefer a two-column desktop layout only where it improves scanning: primary intake form on the left, compact requirements/status support on the right; stack cleanly on small screens.
- Reduce all-caps decorative labels and long explanatory copy in the affected areas.

## Files to modify
- `frontend/src/components/Tabs.tsx`
- `frontend/src/components/DataIntakePage.tsx`
- `frontend/src/components/ui.tsx` for quieter shared styling or variants of `LifecycleStepper` / `DisclosurePanel` if that is cleaner than duplicating local markup.
- Potentially `frontend/src/index.css` only if a small reusable app-surface class is preferable to repeated Tailwind strings.

## Reuse
- Reuse existing tab IDs/types from `frontend/src/types/doe.ts` through `Tabs.tsx`.
- Reuse existing `createIngestionSession` flow and account/project/workspace logic in `DataIntakePage.tsx`.
- Reuse existing `DisclosurePanel` only if its current bordered card styling is acceptable after surrounding flattening; otherwise avoid it or add a quieter variant.
- Reuse `LifecycleStepper` semantics if possible, but likely restyle or replace its use on Data Intake with a compact horizontal progress indicator.

## Steps
- [ ] Restyle `Tabs.tsx` sidebar shell to be quieter: thinner/no heavy border, reduced shadow, smaller radius, calmer spacing.
- [ ] Remove sidebar group subtitles and per-item descriptions in expanded mode; keep group titles and labels.
- [ ] Convert inactive nav items to text/icon-like rows with transparent borders and minimal hover treatment.
- [ ] Convert active nav item to one selected state: blue 2px left rail, subtle blue-tinted background, stronger text, no glow/heavy outline.
- [ ] Preserve collapsed sidebar behavior, but make collapsed items simple initials with the same left/accent selected treatment.
- [ ] Restructure Data Intake from one large `SectionCard` into flat page sections separated by whitespace/dividers.
- [ ] Replace the chunky lifecycle cards with a compact progress line/step row suitable for onboarding status; update `LifecycleStepper` globally or add a variant if needed.
- [ ] Keep the upload/package area as the primary meaningful surface, but reduce nesting inside it.
- [ ] Replace radio mini-cards with compact segmented controls or inline radio rows.
- [ ] Make form labels sentence/title case where possible and reduce uppercase/tracking usage.
- [ ] Restyle package requirements/templates as a flatter side panel or inline checklist, not multiple competing cards; update `DisclosurePanel` globally or add a quieter variant if appropriate.
- [ ] Keep error, storage-blocked, workspace setup, and session-created messages visible but less card-heavy.
- [ ] Audit resulting Data Intake DOM for nested bordered containers and remove any unnecessary border-inside-border patterns.

## Verification
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Manually check Data Intake in these states: no projects, existing projects, workspace blocked, file selected, upload error, session created.
- [ ] Manually check sidebar expanded/collapsed, active state, hover states, keyboard focus, and tab switching.
- [ ] Confirm no other app pages were intentionally restyled beyond shared components if modified.

## Decisions from user
- Use whichever Data Intake structure improves experience/readability and feels least AI-generated; prefer the layout that best supports scanning rather than preserving the current structure.
- Keep sidebar collapse behavior.
- Shared component styling/variants may be changed if useful.
