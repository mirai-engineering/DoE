from __future__ import annotations

import argparse
from pathlib import Path

from ml_lifecycle.ingesting.generic_tabular_doe.preprocessing import build_generic_preprocessing_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess a Mirai-contract generic tabular project")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--canonical-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_generic_preprocessing_artifacts(raw_root=args.raw_root, canonical_dir=args.canonical_dir, artifact_dir=args.artifact_dir, project_id=args.project_id)
    print(result)


if __name__ == "__main__":
    main()
