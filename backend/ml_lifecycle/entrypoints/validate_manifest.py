from __future__ import annotations

import argparse
from pathlib import Path

from ml_lifecycle.ingesting.generic_tabular_doe.contract import load_and_validate_contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a Mirai manifest/data-dictionary contract")
    parser.add_argument("--raw-root", type=Path, required=True)
    args = parser.parse_args()
    contract = load_and_validate_contract(args.raw_root)
    print({"status": "valid", "template_id": contract.get("project", {}).get("template_id"), "columns": len(contract.get("columns", []))})


if __name__ == "__main__":
    main()
