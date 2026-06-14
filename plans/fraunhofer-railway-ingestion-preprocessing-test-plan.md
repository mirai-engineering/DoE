# Fraunhofer Railway ingestion and preprocessing test plan

## Context

We need to validate the newly deployed Railway `generic_tabular_doe` intake/preprocessing flow with Fraunhofer PEM fuel-cell data. The approved workflow is:

1. Clean all Railway-side training/intake/artifact data so the test starts from a known empty runtime state, while preserving the Railway services themselves.
2. Recompute the Fraunhofer cathode catalyst degradation Cell_01 data from raw files into a Mirai contract package.
3. Write the generated `fraunhofer2miraicontract` package under `./backend/docs/examples/fuel-cell/`.
4. Upload that generated package through the app and confirm ingestion and preprocessing work on Railway.

Important execution constraint:
- Railway actions that delete data/artifacts are destructive and must stay scoped to Railway runtime data only. Preserve Railway services/resources and do not delete local data.

## Agent and skill mapping

- Repo instruction source: `AGENTS.md` was read before drafting this plan.
- Configured skills inspected: `.pi/skills/use-railway/SKILL.md`, Clerk skills, GitHub workflow skill.
- `use-railway`: use for read-only Railway status/log/variable checks and, after explicit approval, scoped cleanup verification.
- `clerk-*` skills: only needed if upload/test requires authenticated browser/API setup troubleshooting.
- `github-mcp-workflow`: not needed for local generation unless we later open PRs/issues.
- Scout/read-only discovery: use for implementation handoff to verify existing converter/extractor utilities before editing or running cleanup.

## Current discoveries

- Fraunhofer evaluation scripts are under `data/Cathode Catalyst Degradation/03-Evaluation_scripts`:
  - `eval_CV.py`: computes ECSA and double-layer capacitance from corrected CV cycles.
  - `eval_limiting_current.py`: computes O2 mass-transport resistance from limiting-current data.
  - `eval_LSV.py`: computes H2 crossover current from LSV by linear extrapolation.
  - `eval_EIS_H2N2.py`: fits H2/N2 EIS with a transmission-line model for `R_ion`, `C_dl`, and `HFR`.
- Existing repo PEM builder already implements the main paper-shaped supervised table in `backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/ingest.py`.
- Existing reference table: `data/reference/pem_fuel_cell_cathode_degradation/model_table.csv` has 2,544 rows and 29 columns.
- Existing model grain is polarization-point rows:
  - inputs: material/AST/operating variables + voltage.
  - outputs: BoL current density, EoL current density, BoL ECSA, ECSA loss.
- Current deployed Mirai contract requires new fixed-source packages to use internal variable IDs `x1..xN` and `y1..yM`, with semantic names preserved as `source_name` and `ui_label`.
- `backend/docs/` does not currently exist; the implementation should create `backend/docs/examples/fuel-cell/` for the generated package if approved.
- PDF text extraction was attempted with available local tools, but `pdftotext` and Python PDF libraries are not installed and macOS `textutil` returned compressed PDF internals. The implementation should use an available non-runtime extraction method/tool to read the PDF for parity notes, or document that PDF extraction is blocked by local tooling.

## Approach

Create a local `fraunhofer2miraicontract` fixed-source-table package that uses the existing Fraunhofer builder outputs but packages them as the generic Mirai contract:

- `mirai_manifest.json`
- `data_dictionary.csv`
- `experiments.csv`
- `conditions.csv`
- `results.csv`

Recommended package shape:

- `experiments.csv`: one row per cell/test/material/AST condition.
- `conditions.csv`: one row per modelable operating condition, especially RH + voltage point.
- `results.csv`: one row per result point with BoL/EoL current and ECSA outputs.
- `data_dictionary.csv`: maps semantic source columns to generic internal IDs:
  - `x1`: Pt/C ratio
  - `x2`: I/C ratio
  - `x3`: Ionomer EW
  - `x4`: Operating RH
  - `x5`: Operating voltage
  - `x6`: AST RH
  - `x7`: AST UPL
  - `y1`: BoL current density
  - `y2`: EoL current density
  - `y3`: BoL ECSA
  - `y4`: ECSA loss

For this Railway app test, recompute the Cell_01 supervised table from raw `01-Data/Cell_01` files using the existing audited builder, then split that table into fixed Mirai source tables. Preserve provenance columns so preprocessing can regenerate a canonical `model_table.csv` comparable to the builder output. Use the Fraunhofer eval scripts and PDF to document future parity/reproduction targets for training and scientific validation.

## Files to modify

Plan only for now. Expected implementation/generation files if approved:

- `scripts/` or `backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/`: add or reuse a converter that emits the fixed Mirai contract package.
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-cell-01/`: generated fixed-source package directory.
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-cell-01.zip`: generated upload ZIP, if we choose to create a ZIP artifact locally.
- Optional docs: `docs/tutorials/` or `docs/reference/` notes on Fraunhofer package generation and upload verification.

## Reuse

- `backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/ingest.py`
  - `build_model_table` already aligns BoL voltage points to EoL by interpolation and outputs the paper-shaped table.
  - Uses `0cycles` vs `30000cycles` IV curves and ECSA scalar outputs.
- `backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/schema.py`
  - Defines paper input/output columns and labels.
- `backend/ml_lifecycle/ingesting/extractors/pem_cell_zip_bundle.py`
  - Existing raw ZIP adapter, useful if later we package raw `Cell_NN.zip` bundles instead of fixed source tables.
- `data/reference/pem_fuel_cell_cathode_degradation/model_table.csv`
  - Current audited reference table for first Railway intake test.
- `backend/tests/fixtures/fuel_cell_fixed_multitable_package/`
  - Existing fixed-source Mirai package structure to mirror.

## Steps

- [ ] Perform read-only Railway inventory: app health, project registry, S3 bucket/object prefixes, Postgres project/training tables, MLflow experiments/runs/models.
- [ ] Delete all Railway-side intake/training/artifact data only after taking inventory, preserving Railway services/resources: app, MLflow service, Postgres service, S3 buckets, variables, domains, and deployments.
- [ ] Confirm cleanup by re-reading Railway Postgres/S3/MLflow state; no local data should be deleted.
- [ ] Extract enough PDF text/figures locally to confirm paper inputs/outputs, reported metrics, and desired parity targets. If current tools cannot extract text, use/document a non-runtime extractor method rather than guessing.
- [ ] Review Fraunhofer eval scripts against existing builder to decide which metrics belong in MVP Mirai training table vs later scientific validation artifacts.
- [ ] Recompute the Cell_01 model table from raw `data/Cathode Catalyst Degradation/01-Data/Cell_01` via the existing builder.
- [ ] Convert the recomputed Cell_01 rows into `experiments.csv`, `conditions.csv`, `results.csv`, `data_dictionary.csv`, and `mirai_manifest.json` under `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-cell-01/`.
- [ ] Validate package locally with the generic contract/preprocessing tests before uploading.
- [ ] Zip the five contract files for upload, excluding raw traces and `.DS_Store` files.
- [ ] User uploads package in the Railway app.
- [ ] Verify Railway ingestion/preprocessing artifacts: generated canonical `model_table.csv`, variable mapping, project detail metadata, and preprocessing review UI.
- [ ] If preprocessing succeeds, run a later training parity plan comparing Railway model results to paper/reference outputs.

## Verification

Read-only/pre-cleanup:

```bash
railway status --json
curl -fsS https://mirai-doe-production.up.railway.app/health
```

Local package validation after generation:

```bash
cd backend && uv run pytest tests/test_generic_contract_pipeline.py -q
```

Railway app validation after upload:

- App upload accepts ZIP/direct package.
- Preprocessing review shows `x1..x7` and `y1..y4` as immutable internal IDs.
- `source_name`/`ui_label` show Fraunhofer domain names.
- Metadata/group/id columns are visible only in review/detail/header contexts, not model controls.
- Canonical `model_table.csv` has expected row count and no missing required X/Y fields.

## Decisions confirmed

- Railway cleanup scope: delete all Railway-side training/intake/artifact data, including MLflow runs/models/artifacts, but preserve Railway services and do not delete local data.
- Package source: recompute from raw Fraunhofer Cell_01 files, not from the existing reference `model_table.csv` alone.
- Initial package size: small Cell_01 smoke package.
- Local generated output path: `backend/docs/examples/fuel-cell/`.
