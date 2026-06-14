# Historical Fuel-Cell Upload Click Path

This document is retained as historical context only.

The current Mirai runtime no longer exposes a separate fuel-cell upload path and no longer asks users to upload `data_overview.xlsx` plus `Cell_NN.zip` archives for preprocessing. Fraunhofer fuel-cell data must be reshaped into the same generic Mirai Experiment Package used for every engineering tabular project:

```text
mirai_manifest.json
data_dictionary.csv
model_table.csv
metadata/        # optional declared overview tables
raw_reference/   # optional audit/source material only
```

Use the generic Data Intake page and upload the Mirai package folder/files, or a ZIP containing the same structure. Runtime preprocessing and training use `generic_tabular_doe`.
