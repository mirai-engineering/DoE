"""Deprecated fuel-cell-specific entrypoint.

The live Mirai app uses generic_tabular_doe and Mirai contract ZIP packages only.
"""


def main() -> None:
    raise SystemExit("Deprecated fuel-cell entrypoint is quarantined; use generic_tabular_doe contract/training flow.")


if __name__ == "__main__":
    main()
