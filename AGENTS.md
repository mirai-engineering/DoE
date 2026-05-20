# Project Instructions

- This repo uses uv, not pip.
- Backend runs with FastAPI.
- Frontend uses React + Vite.
- Keep Docker workflow intact.
- Do not rename public API routes unless explicitly asked.
- When changing UI, preserve current branding and layout structure.
- After changes, suggest the exact local test command.
- Before creating, revising, approving, executing, or completing any Plannotator/implementation plan, read and follow `.pi/skills/plannotator-plan-workflow/SKILL.md`.
- Store new agent implementation plans under `docs/agent-plans/to-implement/`.
- Once a Plannotator plan is implemented and validated, move it automatically to `docs/agent-plans/implemented/`.
- Do not create root-level `plans/` files for implementation plans.
- Treat `generic_tabular_doe` as the source-of-truth lifecycle for MVP tabular DoE: preprocessing artifacts, train/validation/test split semantics, MLflow run/model registration, model-quality artifacts, serving resolution, BO observations, and UI behavior should follow the generic path first.
- The Fraunhofer/PEM fuel-cell demo should mimic the generic Mirai path after intake: its only domain-specific difference is the `pem_cell_zip_bundle` extractor/adapter that converts the PEM ZIP bundle into the canonical Mirai contract tables before running the generic workflow. Do not create a separate fuel-cell lifecycle behavior unless explicitly requested.
- Client/workspace separation is metadata and storage layout, not Python package forks: “Mirai Engineering” should represent strict generic-contract projects; “Fraunhofer” should demonstrate the same generic lifecycle with the PEM extractor adapter.
