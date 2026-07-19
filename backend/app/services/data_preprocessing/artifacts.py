"""Data preprocessing artifact naming helpers.

Keep these names stable; downstream ML preprocessing and training rely on them.
"""

CANONICAL_MODEL_TABLE = "canonical/model_table.csv"
TRAINING_SCHEMA = "training_latest/schema.json"
TRAINING_PREPROCESSING = "training_latest/preprocessing.json"
TRAINING_SPLIT_REPORT = "training_latest/split_report.json"
TRAINING_VALIDATION_REPORT = "training_latest/validation_report.json"
