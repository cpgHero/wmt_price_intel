"""Command-line entry point for contract validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from rci_contracts.validator import ContractError, validate_handoff


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate RCI JSON contracts and fixtures.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (defaults to the current directory).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validated = validate_handoff(args.root.resolve())
    except ContractError as exc:
        print(str(exc))
        return 1
    print(f"Validated {validated} JSON contract documents.")
    return 0
