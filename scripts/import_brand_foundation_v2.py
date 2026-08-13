#!/usr/bin/env python3
"""Build the immutable v2 brand-universe foundation from reviewed source artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
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
RETAILER_CONTEXT_MAP = {
    "ALDI": "aldi_us",
    "H-E-B": "heb_us",
    "Kroger": "kroger_us",
    "Target": "target_us",
    "Walmart": "walmart_us",
    "Whole Foods Market": "whole_foods_market_us",
}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _none_if_blank(value: Any) -> Any:
    return None if value in (None, "") else value


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if str(value).casefold() in {"true", "1", "yes"}:
        return True
    if str(value).casefold() in {"false", "0", "no"}:
        return False
    raise ValueError(f"cannot coerce {value!r} to a boolean")


def _csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _sheet_rows(workbook: dict[str, Any], sheet: str) -> list[dict[str, Any]]:
    values = workbook[sheet]["values"]
    header = [str(value) for value in values[3]]
    return [dict(zip(header, row, strict=False)) for row in values[4:] if row[0]]


def _normalized_source_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    normalized = str(value).strip()
    if normalized.casefold() in {"true", "false"}:
        return normalized.casefold()
    return normalized


def _assert_source_rows_match(
    label: str,
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    id_field: str,
) -> None:
    def indexed(rows: list[dict[str, Any]]) -> dict[str, dict[str, str | None]]:
        return {
            str(row[id_field]): {key: _normalized_source_value(value) for key, value in row.items()}
            for row in rows
        }

    if indexed(left) != indexed(right):
        raise ValueError(f"{label} source representations do not reconcile exactly")


def _private_brands(workbook: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in _sheet_rows(workbook, "Private_Label_Master"):
        row = dict(source)
        source_retailer_id = str(row["retailer_id"])
        row["source_retailer_id"] = source_retailer_id
        row["retailer_id"] = RETAILER_ID_MAP[source_retailer_id]
        for field in ("in_private_label_matching", "is_grocery_relevant", "retailer_exclusive"):
            row[field] = _bool(row[field])
        for field in ("first_seen_at", "last_seen_at", "last_verified_at"):
            row[field] = _none_if_blank(row.get(field))
        row["notes"] = str(row.get("notes") or "")
        output.append(row)
    return output


def _external_brands(path: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in _csv_rows(path):
        row = dict(source)
        row["is_priority_brand"] = _bool(row.pop("is_priority_dairy_egg"))
        for field in ("core_region", "home_state", "corroborating_source_ids", "notes"):
            row[field] = _none_if_blank(row.get(field))
        row["last_verified_at"] = _none_if_blank(row.get("last_verified_at"))
        output.append(row)
    return output


def _aliases(
    workbook: dict[str, Any],
    canonical_ids: dict[str, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}
    for source in _sheet_rows(workbook, "Brand_Aliases"):
        namespace = str(source["alias_namespace"])
        source_context = str(source.get("retailer_context") or "global")
        retailer_id = (
            RETAILER_CONTEXT_MAP[source_context] if namespace == "private_label" else "__global__"
        )
        base_id = f"alias__{namespace}__{retailer_id}__{source['alias_normalized']}"
        seen_ids[base_id] = seen_ids.get(base_id, 0) + 1
        alias_id = base_id if seen_ids[base_id] == 1 else f"{base_id}__{seen_ids[base_id]}"
        source_reference = _none_if_blank(source.get("source_reference"))
        output.append(
            {
                "alias_id": alias_id,
                "source_alias_id": alias_id,
                "source_retailer_id": source_context,
                "retailer_id": retailer_id,
                "retailer": source_context if retailer_id != "__global__" else "Global",
                "alias_name": str(source["alias_name"]),
                "alias_normalized": str(source["alias_normalized"]),
                "canonical_brand_id": canonical_ids.get(
                    str(source["canonical_brand_id"]), str(source["canonical_brand_id"])
                ),
                "canonical_brand_name": str(source["canonical_brand_name"]),
                "alias_type": str(source["alias_type"]),
                "status": "Active",
                "matching_rule": str(source["matching_rule"]),
                "confidence": str(source["confidence"]),
                "source_url": (
                    source_reference
                    if isinstance(source_reference, str)
                    and source_reference.startswith(("http://", "https://"))
                    else None
                ),
                "notes": _none_if_blank(source.get("notes")),
                "alias_namespace": namespace,
                "category_context": _none_if_blank(source.get("category_context")),
                "source_reference": source_reference,
            }
        )
    return output


def _presence(workbook: dict[str, Any]) -> list[dict[str, Any]]:
    retailer_columns = {
        "Walmart": "walmart_us",
        "ALDI": "aldi_us",
        "H-E-B": "heb_us",
        "Target": "target_us",
        "Kroger": "kroger_us",
        "Whole Foods Market": "whole_foods_market_us",
    }
    return [
        {
            "brand_id": str(row["brand_id"]),
            "presence": {
                retailer_id: str(row[column]) for column, retailer_id in retailer_columns.items()
            },
            "presence_rule": str(row["presence_rule"]),
            "last_verified_at": _none_if_blank(row.get("last_verified_at")),
        }
        for row in _sheet_rows(workbook, "Retailer_Presence_Seed")
    ]


def _source_registry(path: Path) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "verified_at": _none_if_blank(row.get("verified_at")),
            "evidence_notes": _none_if_blank(row.get("evidence_notes")),
        }
        for row in _csv_rows(path)
    ]


def build(args: argparse.Namespace) -> dict[str, Any]:
    universe = json.loads(args.universe_json.read_text(encoding="utf-8"))
    workbook = json.loads(args.workbook_values.read_text(encoding="utf-8"))
    _assert_source_rows_match(
        "brand universe JSON/CSV",
        universe,
        _csv_rows(args.universe_csv),
        id_field="universe_brand_id",
    )
    _assert_source_rows_match(
        "brand universe JSON/workbook",
        universe,
        _sheet_rows(workbook, "Brand_Universe_Master"),
        id_field="universe_brand_id",
    )
    _assert_source_rows_match(
        "regional/national CSV/workbook",
        _csv_rows(args.regional_national_csv),
        _sheet_rows(workbook, "Regional_National_Master"),
        id_field="brand_id",
    )
    _assert_source_rows_match(
        "priority dairy/egg CSV/workbook",
        _csv_rows(args.priority_csv),
        _sheet_rows(workbook, "Priority_Dairy_Eggs"),
        id_field="brand_id",
    )
    _assert_source_rows_match(
        "source registry CSV/workbook",
        _csv_rows(args.source_registry_csv),
        _sheet_rows(workbook, "Source_Registry"),
        id_field="source_id",
    )
    external = _external_brands(args.regional_national_csv)
    private_brands = _private_brands(workbook)
    private_universe_ids = {
        f"private_label__{row['source_retailer_id']}__{row['brand_name_normalized']}": str(
            row["brand_id"]
        )
        for row in private_brands
    }
    universe_ids = {str(row["universe_brand_id"]) for row in universe}
    expected_ids = set(private_universe_ids) | {str(row["brand_id"]) for row in external}
    if universe_ids != expected_ids:
        raise ValueError("unified brand universe does not reconcile to the governed source masters")
    priority_rows = _csv_rows(args.priority_csv)
    priority_ids = sorted(str(row["brand_id"]) for row in priority_rows)
    flagged_priority_ids = sorted(
        str(row["brand_id"]) for row in external if row["is_priority_brand"]
    )
    if priority_ids != flagged_priority_ids:
        raise ValueError("priority dairy/egg file does not reconcile to external master flags")
    source_aliases = _aliases(workbook, private_universe_ids)
    aliases_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in source_aliases:
        aliases_by_key.setdefault(
            (str(row["retailer_id"]), str(row["alias_normalized"])), []
        ).append(row)
    alias_conflicts = [
        {
            "retailer_id": retailer_id,
            "alias_normalized": normalized,
            "candidate_brand_ids": sorted(
                {str(row["canonical_brand_id"]) for row in candidate_rows}
            ),
            "resolution": "quarantined_unresolved",
        }
        for (retailer_id, normalized), candidate_rows in sorted(aliases_by_key.items())
        if len({str(row["canonical_brand_id"]) for row in candidate_rows}) > 1
    ]
    conflicting_keys = {
        (str(row["retailer_id"]), str(row["alias_normalized"])) for row in alias_conflicts
    }
    approved_aliases = [
        row
        for row in source_aliases
        if (str(row["retailer_id"]), str(row["alias_normalized"])) not in conflicting_keys
    ]
    return {
        "schema_version": "2.0.0",
        "id": "cpg_brand_foundation",
        "name": "CPGHero Brand Universe Foundation",
        "version": "2.0.0",
        "status": "active",
        "source_artifacts": [
            {
                "name": args.universe_json.name,
                "sha256": _checksum(args.universe_json),
                "role": "authoritative_master",
            },
            {
                "name": args.universe_csv.name,
                "sha256": _checksum(args.universe_csv),
                "role": "review_view",
            },
            {
                "name": args.regional_national_csv.name,
                "sha256": _checksum(args.regional_national_csv),
                "role": "authoritative_master",
            },
            {
                "name": args.priority_csv.name,
                "sha256": _checksum(args.priority_csv),
                "role": "review_view",
            },
            {
                "name": args.source_registry_csv.name,
                "sha256": _checksum(args.source_registry_csv),
                "role": "authoritative_master",
            },
            {
                "name": args.workbook.name,
                "sha256": _checksum(args.workbook),
                "role": "authoritative_aliases",
            },
        ],
        "retailer_id_map": RETAILER_ID_MAP,
        "brands": private_brands,
        "external_brands": external,
        "aliases": approved_aliases,
        "alias_conflicts": alias_conflicts,
        "priority_brand_ids": priority_ids,
        "retailer_presence": _presence(workbook),
        "source_registry": _source_registry(args.source_registry_csv),
        "agent_instructions": [
            {
                "rule_id": str(row["rule_id"]),
                "topic": str(row["topic"]),
                "instruction": str(row["instruction"]),
            }
            for row in _sheet_rows(workbook, "Agent_Instructions")
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-json", type=Path, required=True)
    parser.add_argument("--universe-csv", type=Path, required=True)
    parser.add_argument("--regional-national-csv", type=Path, required=True)
    parser.add_argument("--priority-csv", type=Path, required=True)
    parser.add_argument("--source-registry-csv", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--workbook-values", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"{json.dumps(document, ensure_ascii=False, indent=2)}\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
