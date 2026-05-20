from __future__ import annotations

import argparse
from pathlib import Path

from ml_lifecycle.training.generic_tabular_doe.train import train_generic_project


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a Mirai-contract generic tabular project")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    result = train_generic_project(project_id=args.project_id, data_dir=args.data_dir, artifact_dir=args.artifact_dir)
    print(result)


if __name__ == "__main__":
    main()
