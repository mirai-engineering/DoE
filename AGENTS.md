# The MIRAI DoE
This is an AI-powered Design of Experiments platform for industrial R&D teams. It helps engineers optimize complex systems (fuel cells, batteries, manufacturing processes, materials, etc.) by combining experimental data, surrogate modeling, and Bayesian optimization to recommend the next best experiments. The product is designed for real-world industrial constraints: sparse datasets, limited budgets, domain expertise, and strict IP/privacy requirements. Agents should prioritize scientific rigor, explainability, and practical business value over academic benchmark performance.
# Project Instructions
- This repo uses uv, not pip.
- Frontend uses React + Vite.
- Keep Docker workflow intact unless explicitely asked to change.
- Do not rename public API routes unless explicitly asked.
- When changing UI, preserve current branding and layout structure.
- After changes, suggest the exact local test command.
- Treat `generic_tabular_doe` as the source-of-truth lifecycle for MVP tabular DoE: preprocessing artifacts, train/validation/test split semantics, MLflow run/model registration, model-quality artifacts, serving resolution, BO observations, and UI behavior should follow the generic path first.
- The Fraunhofer/PEM fuel-cell demo should mimic the generic Mirai path after intake: its only domain-specific difference is the `pem_cell_zip_bundle` extractor/adapter that converts the PEM ZIP bundle into the canonical Mirai contract tables before running the generic workflow. Do not create a separate fuel-cell lifecycle behavior unless explicitly requested.
- Client/workspace separation is metadata and storage layout, not Python package forks: “Mirai Engineering” should represent strict generic-contract projects; “Fraunhofer” should demonstrate the same generic lifecycle with the PEM extractor adapter.
# Before implementation, run an agent chain and use the scout agent whenever possible:
Start with a scout/read-only discovery step to bootstrap-script state before editing. Use the scout output to confirm the implementation tasks are still valid and to avoid duplicating existing utilities. Then run focused implementation/review steps or the current task at hand. If an agent runner is available, first list configured agents/chains and choose the available scout-style agent/chain; do not invent an agent name if none is configured.
# Skill mapping for plans
Whenever creating a plan, check all skills available and map the skills meaningfully to each task to maximize efficiency
