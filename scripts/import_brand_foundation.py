#!/usr/bin/env python3
"""Build the immutable brand-foundation document from the supplied handoff artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

RETAILER_ID_MAP = {
    "aldi_us": "aldi_us",
    "heb": "heb_us",
    "kroger": "kroger_us",
    "target": "target_us",
    "walmart": "walmart_us",
    "whole_foods_market": "whole_foods_market_us",
}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _none_if_blank(value: Any) -> Any:
    return None if value in (None, "") else value


def _aliases(workbook_values_path: Path) -> list[dict[str, Any]]:
    workbook = json.loads(workbook_values_path.read_text(encoding="utf-8"))
    values = workbook["Brand_Aliases"]["values"]
    header = [str(value) for value in values[3]]
    source_rows = [dict(zip(header, row, strict=False)) for row in values[4:] if row[0]]
    id_counts: Counter[str] = Counter()
    output: list[dict[str, Any]] = []
    for row in source_rows:
        source_retailer_id = str(row["retailer_id"])
        source_alias_id = str(row["alias_id"])
        id_counts[source_alias_id] += 1
        alias_id = source_alias_id
        if id_counts[source_alias_id] > 1:
            alias_id = f"{source_alias_id}__{id_counts[source_alias_id]}"
        output.append(
            {
                "alias_id": alias_id,
                "source_alias_id": source_alias_id,
                "source_retailer_id": source_retailer_id,
                "retailer_id": RETAILER_ID_MAP[source_retailer_id],
                "retailer": str(row["retailer"]),
                "alias_name": str(row["alias_name"]),
                "alias_normalized": str(row["alias_normalized"]),
                "canonical_brand_id": str(row["canonical_brand_id"]),
                "canonical_brand_name": str(row["canonical_brand_name"]),
                "alias_type": str(row["alias_type"]),
                "status": str(row["status"]),
                "matching_rule": str(row["matching_rule"]),
                "confidence": str(row["confidence"]),
                "source_url": _none_if_blank(row.get("source_url")),
                "notes": _none_if_blank(row.get("notes")),
            }
        )
    return output


def build(args: argparse.Namespace) -> dict[str, Any]:
    master = json.loads(args.master_json.read_text(encoding="utf-8"))
    brands: list[dict[str, Any]] = []
    for source in master:
        row = dict(source)
        source_retailer_id = str(row["retailer_id"])
        row["source_retailer_id"] = source_retailer_id
        row["retailer_id"] = RETAILER_ID_MAP[source_retailer_id]
        for field in ("first_seen_at", "last_seen_at", "last_verified_at"):
            row[field] = _none_if_blank(row.get(field))
        brands.append(row)
    return {
        "schema_version": "1.0.0",
        "id": "private_label_brand_foundation",
        "name": "CPGHero Private Label Brand Foundation",
        "version": "1.0.0",
        "status": "active",
        "source_artifacts": [
            {
                "name": args.master_json.name,
                "sha256": _checksum(args.master_json),
                "role": "authoritative_master",
            },
            {
                "name": args.master_csv.name,
                "sha256": _checksum(args.master_csv),
                "role": "review_view",
            },
            {
                "name": args.workbook.name,
                "sha256": _checksum(args.workbook),
                "role": "authoritative_aliases",
            },
            {
                "name": args.instructions.name,
                "sha256": _checksum(args.instructions),
                "role": "instructions",
            },
        ],
        "retailer_id_map": RETAILER_ID_MAP,
        "brands": brands,
        "aliases": _aliases(args.workbook_values),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master-json", type=Path, required=True)
    parser.add_argument("--master-csv", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--workbook-values", type=Path, required=True)
    parser.add_argument("--instructions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"{json.dumps(document, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
