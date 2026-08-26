#!/usr/bin/env python3
"""Merge the reviewed vitamin brand package into the immutable brand foundation.

The package's canonical data is accepted only after checksum, shape, key, and
foreign-key reconciliation.  Embedded implementation instructions are not
imported.  Retailer-presence evidence remains descriptive and never becomes
product/store availability authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]

CATEGORY_CONTEXT = "Vitamins & Supplements"
FOUNDATION_VERSION = "2.1.0"

RETAILER_ID_MAP = {
    "albertsons": "albertsons_us",
    "aldi": "aldi_us",
    "amazon": "amazon_us_same_day",
    "bjs": "bjs_us",
    "costco": "costco_us",
    "cvs": "cvs_us",
    "giant_eagle": "giant_eagle_us",
    "heb": "heb_us",
    "kroger": "kroger_us",
    "meijer": "meijer_us",
    "safeway": "safeway_us",
    "sams_club": "sams_club_us",
    "shoprite": "shoprite_us",
    "target": "target_us",
    "trader_joes": "trader_joes_us",
    "walgreens": "walgreens_us",
    "walmart": "walmart_us",
    "wegmans": "wegmans_us",
}

RETAILER_CONTEXT_MAP = {
    "Albertsons": "albertsons_us",
    "ALDI": "aldi_us",
    "Amazon": "amazon_us_same_day",
    "BJ's": "bjs_us",
    "Costco": "costco_us",
    "CVS": "cvs_us",
    "Giant Eagle": "giant_eagle_us",
    "H-E-B": "heb_us",
    "Kroger": "kroger_us",
    "Meijer": "meijer_us",
    "Safeway": "safeway_us",
    "Sam's Club": "sams_club_us",
    "ShopRite": "shoprite_us",
    "Target": "target_us",
    "Trader Joe's": "trader_joes_us",
    "Walgreens": "walgreens_us",
    "Walmart": "walmart_us",
    "Wegmans": "wegmans_us",
}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _none_if_blank(value: Any) -> Any:
    return None if value in (None, "") else value


def _normalize_brand_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii").casefold()
    normalized = ascii_value.replace("&", " and ")
    normalized = normalized.replace("'", "").replace("\N{RIGHT SINGLE QUOTATION MARK}", "")
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", normalized)).strip("_")


def _source_rows(document: JsonObject, name: str) -> list[JsonObject]:
    rows = document["tables"].get(name)
    if not isinstance(rows, list):
        raise ValueError(f"vitamin source is missing table {name!r}")
    return [dict(row) for row in rows]


def _assert_unique(rows: list[JsonObject], fields: tuple[str, ...], label: str) -> None:
    keys = [tuple(str(row.get(field) or "") for field in fields) for row in rows]
    if any(not all(key) for key in keys):
        raise ValueError(f"{label} contains a blank key")
    if len(keys) != len(set(keys)):
        raise ValueError(f"{label} contains duplicate keys")


def _validate_source_package(
    document: JsonObject,
    manifest: JsonObject,
    *,
    document_path: Path,
    workbook_path: Path,
) -> None:
    expected_json_hash = str(manifest["files"]["canonical_json_sha256"])
    expected_workbook_hash = str(manifest["files"]["workbook_sha256"])
    if _checksum(document_path) != expected_json_hash:
        raise ValueError("vitamin canonical JSON checksum does not match the manifest")
    if _checksum(workbook_path) != expected_workbook_hash:
        raise ValueError("vitamin workbook checksum does not match the manifest")

    for specification in manifest["tables"]:
        name = str(specification["table_name"])
        rows = _source_rows(document, name)
        if len(rows) != int(specification["row_count"]):
            raise ValueError(f"{name} row count does not match the manifest")
        if rows and list(rows[0]) != list(specification["columns"]):
            raise ValueError(f"{name} columns do not match the manifest")
        primary_key = specification.get("primary_key")
        if primary_key:
            _assert_unique(rows, (str(primary_key),), name)

    retailers = {str(row["retailer_id"]) for row in _source_rows(document, "Retailer_Master")}
    sources = {str(row["source_id"]) for row in _source_rows(document, "Source_Registry")}
    brands = {
        str(row["universe_brand_id"]) for row in _source_rows(document, "Brand_Universe_Master")
    }
    if retailers != set(RETAILER_ID_MAP):
        raise ValueError("vitamin retailer master does not match the supported retailer mapping")

    private_rows = _source_rows(document, "Private_Label_Master")
    external_rows = _source_rows(document, "Regional_National_Master")
    presence_rows = _source_rows(document, "Retailer_Brand_Presence")
    alias_rows = _source_rows(document, "Brand_Aliases")
    transition_rows = _source_rows(document, "Transition_Log")
    matrix_rows = _source_rows(document, "Retailer_Presence_Matrix")
    _assert_unique(private_rows, ("retailer_id", "brand_name_normalized"), "private labels")
    _assert_unique(external_rows, ("brand_name_normalized",), "external brands")
    _assert_unique(presence_rows, ("retailer_id", "brand_id"), "retailer presence")

    for row in private_rows:
        if str(row["retailer_id"]) not in retailers:
            raise ValueError(f"private label {row['brand_id']!r} references an unknown retailer")
    for row in external_rows:
        if str(row["primary_source_id"]) not in sources:
            raise ValueError(f"external brand {row['brand_id']!r} references an unknown source")
    for row in alias_rows:
        if str(row["canonical_brand_id"]) not in brands:
            raise ValueError(f"alias {row['alias_name']!r} references an unknown brand")
    for row in presence_rows:
        if str(row["retailer_id"]) not in retailers:
            raise ValueError(f"presence {row['presence_id']!r} references an unknown retailer")
        if str(row["brand_id"]) not in brands:
            raise ValueError(f"presence {row['presence_id']!r} references an unknown brand")
        if str(row["source_id"]) not in sources:
            raise ValueError(f"presence {row['presence_id']!r} references an unknown source")
    for row in transition_rows:
        if str(row["canonical_brand_id"]) not in brands:
            raise ValueError(f"transition {row['transition_id']!r} references an unknown brand")
        if str(row["source_id"]) not in sources:
            raise ValueError(f"transition {row['transition_id']!r} references an unknown source")

    positive = defaultdict(lambda: "UNKNOWN")
    for row in presence_rows:
        positive[(str(row["brand_id"]), str(row["retailer"]))] = str(row["presence_status"])
    retailer_names = [str(value) for value in document["metadata"]["retailers"]]
    for row in matrix_rows:
        for retailer_name in retailer_names:
            expected = positive[(str(row["brand_id"]), retailer_name)]
            if str(row[retailer_name]) != expected:
                raise ValueError(
                    f"presence matrix disagrees with source rows for {row['brand_id']!r} "
                    f"at {retailer_name!r}"
                )


def _merge_private_brands(
    base: JsonObject,
    vitamin: JsonObject,
) -> tuple[list[JsonObject], dict[str, str]]:
    output = [dict(row) for row in base["brands"]]
    by_key = {(str(row["retailer_id"]), str(row["brand_name_normalized"])): row for row in output}
    canonical_ids: dict[str, str] = {}
    for source in _source_rows(vitamin, "Private_Label_Master"):
        source_retailer_id = str(source["retailer_id"])
        retailer_id = RETAILER_ID_MAP[source_retailer_id]
        normalized = _normalize_brand_name(str(source["brand_name"]))
        key = (retailer_id, normalized)
        existing = by_key.get(key)
        if existing is not None:
            canonical_ids[str(source["brand_id"])] = str(existing["brand_id"])
            continue
        row = dict(source)
        row["source_retailer_id"] = source_retailer_id
        row["retailer_id"] = retailer_id
        row["brand_name_normalized"] = normalized
        row["first_seen_at"] = _none_if_blank(row.get("first_seen_at"))
        row["last_seen_at"] = _none_if_blank(row.get("last_seen_at"))
        row["last_verified_at"] = _none_if_blank(row.get("last_verified_at"))
        row["notes"] = str(row.get("notes") or "")
        output.append(row)
        by_key[key] = row
        canonical_ids[str(source["brand_id"])] = str(row["brand_id"])
    return output, canonical_ids


def _external_id(source: JsonObject, base_by_normalized: dict[str, JsonObject]) -> str:
    normalized = _normalize_brand_name(str(source["brand_name"]))
    existing = base_by_normalized.get(normalized)
    if existing is None:
        return str(source["brand_id"])
    # A same-name brand with different ownership/category must stay distinct.  The
    # resolver will select this category-scoped identity only inside VMS.
    return f"national__{normalized}_health_products"


def _merge_external_brands(
    base: JsonObject,
    vitamin: JsonObject,
) -> tuple[list[JsonObject], dict[str, str]]:
    output = [dict(row) for row in base.get("external_brands", [])]
    base_by_normalized = {str(row["brand_name_normalized"]): row for row in output}
    canonical_ids: dict[str, str] = {}
    for source in _source_rows(vitamin, "Regional_National_Master"):
        row = dict(source)
        row["brand_id"] = _external_id(source, base_by_normalized)
        row["brand_name_normalized"] = _normalize_brand_name(str(source["brand_name"]))
        row["is_priority_brand"] = str(row["matching_priority"]) in {"Critical", "High"}
        row.pop("is_priority_dairy_egg", None)
        row["core_region"] = _none_if_blank(row.get("core_region"))
        row["home_state"] = _none_if_blank(row.get("home_state"))
        row["corroborating_source_ids"] = _none_if_blank(row.get("corroborating_source_ids"))
        row["last_verified_at"] = _none_if_blank(row.get("last_verified_at"))
        row["notes"] = _none_if_blank(row.get("notes"))
        row["category_context"] = CATEGORY_CONTEXT
        output.append(row)
        canonical_ids[str(source["brand_id"])] = str(row["brand_id"])
    return output, canonical_ids


def _merge_aliases(
    base: JsonObject,
    vitamin: JsonObject,
    canonical_ids: dict[str, str],
    source_urls: dict[str, str],
) -> list[JsonObject]:
    output = [dict(row) for row in base["aliases"]]
    seen_ids = {str(row["alias_id"]) for row in output}
    seen_semantics = {
        (
            str(row["retailer_id"]),
            str(row["alias_normalized"]),
            str(row["canonical_brand_id"]),
            str(row.get("category_context") or ""),
        )
        for row in output
    }
    for source in _source_rows(vitamin, "Brand_Aliases"):
        namespace = str(source["alias_namespace"])
        retailer_id = (
            "__global__"
            if namespace == "Global"
            else RETAILER_CONTEXT_MAP[str(source["retailer_context"])]
        )
        canonical_brand_id = canonical_ids[str(source["canonical_brand_id"])]
        alias_normalized = _normalize_brand_name(str(source["alias_name"]))
        semantic_key = (
            retailer_id,
            alias_normalized,
            canonical_brand_id,
            CATEGORY_CONTEXT,
        )
        if semantic_key in seen_semantics:
            continue
        base_id = f"alias__vitamins__{retailer_id}__{alias_normalized}"
        alias_id = base_id
        suffix = 2
        while alias_id in seen_ids:
            alias_id = f"{base_id}__{suffix}"
            suffix += 1
        source_reference = _none_if_blank(source.get("source_reference"))
        legacy = (
            "legacy" in (f"{source.get('alias_type', '')} {source.get('notes', '')}").casefold()
        )
        output.append(
            {
                "alias_id": alias_id,
                "source_alias_id": alias_id,
                "source_retailer_id": str(source.get("retailer_context") or "global"),
                "retailer_id": retailer_id,
                "retailer": (
                    str(source["retailer_context"]) if retailer_id != "__global__" else "Global"
                ),
                "alias_name": str(source["alias_name"]),
                "alias_normalized": alias_normalized,
                "canonical_brand_id": canonical_brand_id,
                "canonical_brand_name": str(source["canonical_brand_name"]),
                "alias_type": str(source["alias_type"]),
                "status": "Legacy" if legacy else "Active",
                "matching_rule": "exact_normalized_then_category_gate",
                "confidence": str(source["confidence"]),
                "source_url": source_urls.get(str(source_reference)),
                "notes": _none_if_blank(source.get("notes")),
                "alias_namespace": (
                    "regional_national" if retailer_id == "__global__" else "private_label"
                ),
                "category_context": CATEGORY_CONTEXT,
                "source_reference": source_reference,
            }
        )
        seen_ids.add(alias_id)
        seen_semantics.add(semantic_key)
    return output


def _merge_presence(
    base: JsonObject,
    vitamin: JsonObject,
    external_ids: dict[str, str],
) -> list[JsonObject]:
    output = [dict(row) for row in base.get("retailer_presence", [])]
    by_brand: dict[str, dict[str, str]] = defaultdict(dict)
    for source in _source_rows(vitamin, "Retailer_Brand_Presence"):
        if str(source["brand_id"]) not in external_ids:
            continue
        value = str(source["presence_status"])
        # Marketplace-only evidence is intentionally not promoted to retailer
        # assortment presence.  Search/PDP observations remain authoritative.
        status = "PRESENT" if value in {"PRESENT_VERIFIED", "PRESENT_CATEGORY"} else "UNKNOWN"
        by_brand[external_ids[str(source["brand_id"])]][
            RETAILER_ID_MAP[str(source["retailer_id"])]
        ] = status
    all_retailers = sorted(RETAILER_ID_MAP.values())
    source_by_id = {
        str(row["brand_id"]): row for row in _source_rows(vitamin, "Regional_National_Master")
    }
    for source_id, canonical_id in external_ids.items():
        source = source_by_id[source_id]
        output.append(
            {
                "brand_id": canonical_id,
                "presence": {
                    retailer_id: by_brand[canonical_id].get(retailer_id, "UNKNOWN")
                    for retailer_id in all_retailers
                },
                "presence_rule": (
                    "Vitamin category evidence only; PRESENT_MARKETPLACE and missing "
                    "relationships remain UNKNOWN. Search/PDP evidence controls actual assortment."
                ),
                "last_verified_at": _none_if_blank(source.get("last_verified_at")),
            }
        )
    return output


def build(args: argparse.Namespace) -> JsonObject:
    base = json.loads(args.base_foundation.read_text(encoding="utf-8"))
    vitamin = json.loads(args.vitamin_json.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    _validate_source_package(
        vitamin,
        manifest,
        document_path=args.vitamin_json,
        workbook_path=args.workbook,
    )

    brands, private_ids = _merge_private_brands(base, vitamin)
    external_brands, external_ids = _merge_external_brands(base, vitamin)
    canonical_ids = {**private_ids, **external_ids}
    incoming_sources = [dict(row) for row in _source_rows(vitamin, "Source_Registry")]
    source_urls = {str(row["source_id"]): str(row["source_url"]) for row in incoming_sources}
    aliases = _merge_aliases(base, vitamin, canonical_ids, source_urls)
    priority_ids = sorted(
        {
            *[str(value) for value in base.get("priority_brand_ids", [])],
            *[
                str(row["brand_id"])
                for row in external_brands
                if bool(row.get("is_priority_brand"))
            ],
        }
    )
    return {
        **base,
        "name": "CPGHero Cross-Category Brand Universe Foundation",
        "version": FOUNDATION_VERSION,
        "status": "active",
        "source_artifacts": [
            *[dict(row) for row in base["source_artifacts"]],
            {
                "name": args.vitamin_json.name,
                "sha256": _checksum(args.vitamin_json),
                "role": "authoritative_master",
            },
            {
                "name": args.workbook.name,
                "sha256": _checksum(args.workbook),
                "role": "review_view",
            },
            {
                "name": args.manifest.name,
                "sha256": _checksum(args.manifest),
                "role": "authoritative_master",
            },
        ],
        "retailer_id_map": {**base["retailer_id_map"], **RETAILER_ID_MAP},
        "brands": brands,
        "external_brands": external_brands,
        "aliases": aliases,
        "priority_brand_ids": priority_ids,
        "retailer_presence": _merge_presence(base, vitamin, external_ids),
        "source_registry": [
            *[dict(row) for row in base.get("source_registry", [])],
            *incoming_sources,
        ],
        # Deliberately preserve the application's governed instructions.  The
        # attached package's Data_Dictionary_App_Notes are audited as reference
        # material but are not executable application policy.
        "agent_instructions": [dict(row) for row in base.get("agent_instructions", [])],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-foundation", type=Path, required=True)
    parser.add_argument("--vitamin-json", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
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
