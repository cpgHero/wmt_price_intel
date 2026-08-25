#!/usr/bin/env python3
"""Profile distinct-product evidence gaps in a Matching v2 review queue.

This read-only audit distinguishes product-level evidence work from pair-level
review work. It is intentionally standard-library only so it can run in a
worker container without installing development dependencies.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

type JsonObject = dict[str, Any]


def _unknown(value: Any, source: Any) -> bool:
    return value in (None, "", "Unknown", "unknown") or source in (None, "unresolved")


def audit(queue: JsonObject) -> JsonObject:
    cases = list(queue.get("cases") or [])
    products: dict[str, JsonObject] = {}
    case_counts: Counter[str] = Counter()
    missing: defaultdict[str, set[str]] = defaultdict(set)
    conflicts: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    candidate_examples: list[JsonObject] = []

    for case in cases:
        proposal = case.get("engine_proposal") or {}
        statuses[str(proposal.get("status"))] += 1
        tiers[str(proposal.get("tier"))] += 1
        evidence_rows = list((case.get("edge") or {}).get("attribute_evidence") or [])
        for side in ("benchmark", "competitor"):
            listing = case[f"{side}_listing"]
            listing_id = str(listing["listing_id"])
            products[listing_id] = listing
            case_counts[listing_id] += 1
            for row in evidence_rows:
                if row.get("role") != "hard_blocker":
                    continue
                if _unknown(row.get(f"{side}_value"), row.get(f"{side}_source")):
                    missing[listing_id].add(str(row["attribute"]))
        for row in evidence_rows:
            if row.get("role") == "hard_blocker" and row.get("outcome") == "conflict":
                conflicts[str(row["attribute"])] += 1
        if proposal.get("tier"):
            candidate_examples.append(
                {
                    "case_id": case["case_id"],
                    "tier": proposal["tier"],
                    "retailer": case["competitor_retailer_id"],
                    "benchmark": case["benchmark_listing"]["title"],
                    "competitor": case["competitor_listing"]["title"],
                    "attributes": [
                        {
                            "attribute": row["attribute"],
                            "benchmark": row.get("benchmark_value"),
                            "competitor": row.get("competitor_value"),
                            "outcome": row.get("outcome"),
                            "benchmark_source": row.get("benchmark_source"),
                            "competitor_source": row.get("competitor_source"),
                        }
                        for row in evidence_rows
                        if row.get("role") == "hard_blocker"
                        or row.get("attribute") == "package_count"
                    ],
                }
            )

    by_retailer: defaultdict[str, JsonObject] = defaultdict(
        lambda: {
            "products": set(),
            "missing_products": set(),
            "products_with_images": set(),
            "missing_attributes": Counter(),
            "case_appearances": 0,
        }
    )
    for listing_id, listing in products.items():
        retailer_id = str(listing["retailer_id"])
        summary = by_retailer[retailer_id]
        summary["products"].add(listing_id)
        summary["case_appearances"] += case_counts[listing_id]
        if listing.get("image_url") or listing.get("image_urls"):
            summary["products_with_images"].add(listing_id)
        if missing[listing_id]:
            summary["missing_products"].add(listing_id)
            summary["missing_attributes"].update(missing[listing_id])

    return {
        "queue_id": queue.get("queue_id"),
        "queue_version": queue.get("version"),
        "case_count": len(cases),
        "distinct_product_count": len(products),
        "distinct_benchmark_product_count": len(
            {str(case["benchmark_listing_id"]) for case in cases}
        ),
        "distinct_competitor_product_count": len(
            {str(case["competitor_listing_id"]) for case in cases}
        ),
        "products_appearing_in_multiple_cases": sum(
            1 for count in case_counts.values() if count > 1
        ),
        "maximum_case_appearances_per_product": max(case_counts.values(), default=0),
        "mean_case_appearances_per_product": (
            round(sum(case_counts.values()) / len(case_counts), 2) if case_counts else 0
        ),
        "products_missing_hard_evidence": len(missing),
        "products_missing_hard_evidence_excluding_release_profile": sum(
            1 for attributes in missing.values() if attributes - {"release_profile"}
        ),
        "missing_attribute_combinations": dict(
            Counter(",".join(sorted(attributes)) or "none" for attributes in missing.values())
        ),
        "missing_products_with_images": sum(
            1
            for listing_id in missing
            if products[listing_id].get("image_url") or products[listing_id].get("image_urls")
        ),
        "case_statuses": dict(statuses),
        "case_tiers": dict(tiers),
        "known_hard_conflicts": dict(conflicts),
        "by_retailer": {
            retailer_id: {
                "distinct_products": len(summary["products"]),
                "products_missing_hard_evidence": len(summary["missing_products"]),
                "missing_products_with_images": len(
                    summary["products_with_images"] & summary["missing_products"]
                ),
                "case_appearances": summary["case_appearances"],
                "missing_attributes": dict(summary["missing_attributes"]),
            }
            for retailer_id, summary in sorted(by_retailer.items())
        },
        "most_reused_products": [
            {
                "listing_id": listing_id,
                "retailer_id": products[listing_id]["retailer_id"],
                "title": products[listing_id]["title"],
                "case_count": count,
                "missing_hard_attributes": sorted(missing[listing_id]),
            }
            for listing_id, count in case_counts.most_common(25)
        ],
        "missing_product_examples_by_attribute": {
            attribute: [
                {
                    "listing_id": listing_id,
                    "retailer_id": products[listing_id]["retailer_id"],
                    "title": products[listing_id]["title"],
                    "case_count": case_counts[listing_id],
                    "image_count": len(
                        {
                            str(value)
                            for value in (
                                products[listing_id].get("image_url"),
                                *(products[listing_id].get("image_urls") or []),
                            )
                            if value
                        }
                    ),
                    "all_missing_hard_attributes": sorted(missing[listing_id]),
                }
                for listing_id in sorted(
                    (
                        listing_id
                        for listing_id, attributes in missing.items()
                        if attribute in attributes
                    ),
                    key=lambda value: (-case_counts[value], value),
                )[:30]
            ]
            for attribute in sorted(
                {attribute for attributes in missing.values() for attribute in attributes}
            )
        },
        "deterministic_candidate_examples": candidate_examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("queue", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.queue.read_text()))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
