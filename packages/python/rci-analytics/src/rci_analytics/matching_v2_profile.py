"""Profile real Search evidence and build deterministic Matching v2 review queues."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching_v2 import ListingEvidence
from rci_analytics.matching_v2_review import (
    MatchingV2ReviewSampling,
    build_matching_v2_review_queue,
)
from rci_analytics.matching_v2_shadow import (
    ListingEvidenceAccumulatorV2,
    MatchingShadowEvaluatorV2,
)
from rci_analytics.models import JsonObject
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.pdp_attributes import complete_attributes_from_pdp
from rci_analytics.product_pack import ProductPackLoader
from rci_retailer_packs import GovernedBrandResolver, GovernedSellerResolver


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class MatchingV2SourceInput:
    path: Path
    expected_retailer_id: str | None = None


@dataclass(slots=True)
class _RetailerProfile:
    source_rows: int = 0
    normalized_rows: int = 0
    duplicate_rows: int = 0
    positive_price_rows: int = 0
    in_scope_rows: int = 0
    out_of_scope_reasons: Counter[str] = field(default_factory=Counter)
    product_ids: set[str] = field(default_factory=set)
    in_scope_product_ids: set[str] = field(default_factory=set)
    location_keys: set[str] = field(default_factory=set)
    in_scope_location_keys: set[str] = field(default_factory=set)


def _location_key(retailer_id: str, store_number: str | None, zipcode: str | None) -> str | None:
    if store_number:
        return f"{retailer_id}|store|{store_number}"
    if zipcode:
        return f"{retailer_id}|zip|{zipcode}"
    return None


def _source_reference(path: Path, checksum: str) -> str:
    return f"source-file:{path.name}#sha256={checksum}"


def _pdp_archive_reference(path: Path, checksum: str) -> str:
    return f"pdp-archive:{path.name}#sha256={checksum}"


def _pdp_context_from_archives(
    paths: tuple[Path, ...],
) -> tuple[dict[str, JsonObject], list[JsonObject], dict[str, set[str]]]:
    contexts: dict[str, JsonObject] = {}
    observed_at: dict[str, str] = {}
    sources: list[JsonObject] = []
    retailer_references: dict[str, set[str]] = defaultdict(set)
    for source_path in paths:
        path = source_path.resolve()
        digest = _file_checksum(path)
        reference = _pdp_archive_reference(path, digest)
        retailer_counts: Counter[str] = Counter()
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            snapshots = manifest.get("snapshots", [])
            for snapshot in sorted(
                snapshots,
                key=lambda value: str(value.get("observed_at") or ""),
            ):
                if int(snapshot.get("http_status") or 0) != 200:
                    continue
                retailer_id = str(snapshot.get("retailer_id") or "")
                product_id = str(snapshot.get("retailer_product_id") or "")
                response_file = str(snapshot.get("response_file") or "")
                if not retailer_id or not product_id or not response_file:
                    continue
                try:
                    payload = json.loads(archive.read(response_file))
                except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(payload, dict) or not payload.get("name"):
                    continue
                key = f"{retailer_id}:{product_id}"
                timestamp = str(snapshot.get("observed_at") or "")
                if key in contexts and timestamp < observed_at[key]:
                    continue
                category = payload.get("category")
                if category is None and isinstance(payload.get("extras"), dict):
                    category = payload["extras"].get("category")
                category_path: object
                if isinstance(category, list):
                    category_path = [
                        str(value.get("name") if isinstance(value, dict) else value)
                        for value in category
                        if value not in (None, "")
                    ]
                else:
                    category_path = category
                contexts[key] = {
                    "name": payload.get("name"),
                    "brand": payload.get("brand"),
                    "seller": payload.get("seller"),
                    "description": payload.get("description_full")
                    or payload.get("description_short"),
                    "category_path": category_path,
                    "identifiers": payload.get("product_identifiers", {}),
                    "specification": payload.get("specification", {}),
                    "physical_properties": payload.get("physical_properties", {}),
                    "variant_configuration": payload.get("variant_configuration", {}),
                    "item_condition": payload.get("item_condition"),
                    "image_url": payload.get("image_primary"),
                    "url": payload.get("url"),
                }
                observed_at[key] = timestamp
                retailer_counts[retailer_id] += 1
                retailer_references[retailer_id].add(reference)
        sources.append(
            {
                "file_name": path.name,
                "sha256": digest,
                "size_bytes": path.stat().st_size,
                "row_count": sum(retailer_counts.values()),
                "declared_retailer_id": None,
                "normalized_retailer_counts": dict(sorted(retailer_counts.items())),
                "evidence_reference": reference,
            }
        )
    return contexts, sources, retailer_references


def _single_source_reference(retailer_id: str, references: set[str]) -> str:
    if not references:
        raise ValueError(f"no immutable source evidence found for {retailer_id!r}")
    if len(references) == 1:
        return next(iter(references))
    ordered = sorted(references)
    return f"source-bundle:{retailer_id}#sha256={_checksum(ordered)}"


def _listing_quality(
    listings: tuple[ListingEvidence, ...],
    attribute_names: tuple[str, ...],
    critical_names: set[str],
) -> JsonObject:
    known = Counter[str]()
    conflicted = Counter[str]()
    sources: dict[str, Counter[str]] = defaultdict(Counter)
    fully_known_critical = 0
    for listing in listings:
        complete = True
        for name in attribute_names:
            value = listing.attributes.get(name)
            if (
                value is not None
                and value.value is not None
                and value.review_status != "conflicted"
            ):
                known[name] += 1
                sources[name][value.source] += 1
            elif value is not None and value.review_status == "conflicted":
                conflicted[name] += 1
            if name in critical_names and (
                value is None or value.value is None or value.review_status == "conflicted"
            ):
                complete = False
        fully_known_critical += complete
    count = len(listings)
    return {
        "listing_count": count,
        "listings_with_all_critical_attributes": fully_known_critical,
        "critical_attribute_completeness_rate": (
            round(fully_known_critical / count, 6) if count else None
        ),
        "attribute_evidence": {
            name: {
                "known_listings": known[name],
                "known_rate": round(known[name] / count, 6) if count else None,
                "conflicted_listings": conflicted[name],
                "sources": dict(sorted(sources[name].items())),
            }
            for name in attribute_names
        },
    }


def _quality_findings(
    total_rows: int,
    normalization_failures: Counter[str],
    expected_retailer_mismatches: int,
    retailer_documents: list[JsonObject],
) -> list[JsonObject]:
    findings: list[JsonObject] = []
    failure_count = sum(normalization_failures.values())
    if failure_count:
        findings.append(
            {
                "severity": "critical" if failure_count / max(total_rows, 1) >= 0.01 else "warning",
                "code": "normalization_failures",
                "message": f"{failure_count} source rows could not be normalized.",
            }
        )
    if expected_retailer_mismatches:
        findings.append(
            {
                "severity": "critical",
                "code": "retailer_identity_mismatch",
                "message": (
                    f"{expected_retailer_mismatches} normalized rows did not match the declared "
                    "source retailer."
                ),
            }
        )
    for document in retailer_documents:
        quality = document["listing_evidence_quality"]
        rate = quality["critical_attribute_completeness_rate"]
        if rate is not None and rate < 0.8:
            findings.append(
                {
                    "severity": "warning",
                    "code": "critical_attribute_evidence_incomplete",
                    "retailer_id": document["retailer_id"],
                    "message": (
                        f"Only {rate:.1%} of {document['retailer_id']} listings have every "
                        "critical matching attribute."
                    ),
                }
            )
    return findings


def build_matching_v2_evidence_profile(
    repository_root: Path,
    *,
    product_pack_id: str,
    benchmark_retailer_id: str,
    inputs: tuple[MatchingV2SourceInput, ...],
    decided_at: str,
    profile_id: str | None = None,
    competitor_retailer_ids: tuple[str, ...] = (),
    per_stratum_limit: int = 40,
    pdp_archives: tuple[Path, ...] = (),
    review_queue_version: str = "1.0.0",
) -> tuple[JsonObject, JsonObject]:
    """Build a data-quality profile and non-authoritative review queue.

    Processing is streaming at the Search placement grain. Only collapsed listing
    evidence and counters are retained, so repeated locations do not multiply PDP
    or semantic-review work.
    """

    if not inputs:
        raise ValueError("matching v2 evidence profiling requires at least one source input")
    datetime.fromisoformat(decided_at.replace("Z", "+00:00"))
    root = repository_root.resolve()
    pack = ProductPackLoader(root).load(product_pack_id)
    selected_profile_id = profile_id or str(
        pack.reporting["decision_rules"]["preferred_scorecard_profile_id"]
    )
    evaluator = MatchingShadowEvaluatorV2(pack, selected_profile_id)
    policy = evaluator.policy
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(root / "config" / "retailer-catalog.json")
    )
    brand_resolver = GovernedBrandResolver.from_repository(root)
    seller_resolver = GovernedSellerResolver.from_repository(root)
    classifier = OfferClassifier(pack, brand_resolver)
    pdp_context, pdp_source_documents, pdp_retailer_references = _pdp_context_from_archives(
        pdp_archives
    )
    accumulator = ListingEvidenceAccumulatorV2(pack)
    retailer_profiles: dict[str, _RetailerProfile] = defaultdict(_RetailerProfile)
    retailer_sources: dict[str, set[str]] = defaultdict(set)
    source_documents: list[JsonObject] = []
    normalization_failures: Counter[str] = Counter()
    seen_offer_ids: set[str] = set()
    expected_retailer_mismatches = 0
    total_rows = 0

    previous_limit = csv.field_size_limit()
    csv.field_size_limit(100 * 1024 * 1024)
    try:
        for source in inputs:
            path = source.path.resolve()
            digest = _file_checksum(path)
            reference = _source_reference(path, digest)
            source_rows = 0
            source_retailers: Counter[str] = Counter()
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise ValueError(f"source CSV has no header: {path}")
                for row in reader:
                    total_rows += 1
                    source_rows += 1
                    try:
                        offer = normalizer.normalize(dict(row))
                    except ValueError as exc:
                        normalization_failures[str(exc)] += 1
                        continue
                    profile = retailer_profiles[offer.retailer_id]
                    profile.source_rows += 1
                    source_retailers[offer.retailer_id] += 1
                    retailer_sources[offer.retailer_id].add(reference)
                    if (
                        source.expected_retailer_id is not None
                        and offer.retailer_id != source.expected_retailer_id
                    ):
                        expected_retailer_mismatches += 1
                        continue
                    if offer.offer_id in seen_offer_ids:
                        profile.duplicate_rows += 1
                        continue
                    seen_offer_ids.add(offer.offer_id)
                    profile.normalized_rows += 1
                    profile.product_ids.add(offer.retailer_product_id)
                    location_key = _location_key(
                        offer.retailer_id, offer.store_number, offer.zipcode
                    )
                    if location_key:
                        profile.location_keys.add(location_key)
                    if offer.price is not None and offer.price > 0:
                        profile.positive_price_rows += 1
                    classified = complete_attributes_from_pdp(
                        classifier.classify(offer),
                        pdp_context.get(f"{offer.retailer_id}:{offer.retailer_product_id}"),
                        classifier=classifier,
                        pack=pack,
                        seller_resolver=seller_resolver,
                    )
                    if classified.in_scope:
                        profile.in_scope_rows += 1
                        profile.in_scope_product_ids.add(offer.retailer_product_id)
                        if location_key:
                            profile.in_scope_location_keys.add(location_key)
                    else:
                        profile.out_of_scope_reasons[classified.scope_reason or "unspecified"] += 1
                    accumulator.add(classified)
            source_documents.append(
                {
                    "file_name": path.name,
                    "sha256": digest,
                    "size_bytes": path.stat().st_size,
                    "row_count": source_rows,
                    "declared_retailer_id": source.expected_retailer_id,
                    "normalized_retailer_counts": dict(sorted(source_retailers.items())),
                    "evidence_reference": reference,
                }
            )
    finally:
        csv.field_size_limit(previous_limit)

    source_documents.extend(pdp_source_documents)
    for retailer_id, references in pdp_retailer_references.items():
        retailer_sources[retailer_id].update(references)

    observed_retailers = sorted(retailer_profiles)
    if benchmark_retailer_id not in retailer_profiles:
        raise ValueError(f"benchmark retailer {benchmark_retailer_id!r} is absent from inputs")
    competitors = competitor_retailer_ids or tuple(
        retailer_id for retailer_id in observed_retailers if retailer_id != benchmark_retailer_id
    )
    missing_competitors = sorted(set(competitors) - set(observed_retailers))
    if missing_competitors:
        raise ValueError(f"competitor retailers are absent from inputs: {missing_competitors}")

    attribute_names = tuple(attribute.name for attribute in policy.attributes)
    critical_names = {attribute.name for attribute in policy.attributes if attribute.critical}
    listings_by_retailer = {
        retailer_id: accumulator.listings(retailer_id) for retailer_id in observed_retailers
    }
    retailer_documents: list[JsonObject] = []
    for retailer_id in observed_retailers:
        profile = retailer_profiles[retailer_id]
        retailer_documents.append(
            {
                "retailer_id": retailer_id,
                "source_rows": profile.source_rows,
                "normalized_unique_rows": profile.normalized_rows,
                "duplicate_rows": profile.duplicate_rows,
                "positive_price_rows": profile.positive_price_rows,
                "in_scope_rows": profile.in_scope_rows,
                "distinct_products": len(profile.product_ids),
                "distinct_in_scope_products": len(profile.in_scope_product_ids),
                "distinct_locations": len(profile.location_keys),
                "distinct_in_scope_locations": len(profile.in_scope_location_keys),
                "out_of_scope_reasons": dict(sorted(profile.out_of_scope_reasons.items())),
                "listing_evidence_quality": _listing_quality(
                    listings_by_retailer[retailer_id], attribute_names, critical_names
                ),
            }
        )

    maximum_candidate_pairs = int((pack.matching_v2 or {}).get("maximum_candidate_pairs", 250_000))
    benchmark_listings = listings_by_retailer[benchmark_retailer_id]
    results = tuple(
        evaluator.evaluate_listings(
            benchmark_listings,
            listings_by_retailer[competitor],
            benchmark_retailer_id=benchmark_retailer_id,
            competitor_retailer_id=competitor,
            decided_at=decided_at,
            maximum_candidate_pairs=maximum_candidate_pairs,
        )
        for competitor in competitors
    )
    benchmark_reference = _single_source_reference(
        benchmark_retailer_id, retailer_sources[benchmark_retailer_id]
    )
    competitor_references = {
        competitor: _single_source_reference(competitor, retailer_sources[competitor])
        for competitor in competitors
    }
    queue = build_matching_v2_review_queue(
        results,
        queue_id=f"{product_pack_id}-matching-v2-release-review",
        queue_version=review_queue_version,
        benchmark_source_reference=benchmark_reference,
        source_references=competitor_references,
        sampling=MatchingV2ReviewSampling(per_stratum_limit=per_stratum_limit),
    )
    findings = _quality_findings(
        total_rows,
        normalization_failures,
        expected_retailer_mismatches,
        retailer_documents,
    )
    document: JsonObject = {
        "schema_version": "2.0.0",
        "profile_id": f"{product_pack_id}-matching-v2-evidence-profile",
        "profile_version": "1.0.0",
        "authoritative": False,
        "product_pack": {"id": pack.id, "version": pack.version},
        "matching_policy": {
            "profile_id": selected_profile_id,
            "version": policy.version,
            "checksum": policy.checksum,
        },
        "benchmark_retailer_id": benchmark_retailer_id,
        "competitor_retailer_ids": list(competitors),
        "decided_at": decided_at,
        "source_files": source_documents,
        "totals": {
            "source_rows": total_rows,
            "normalized_unique_rows": len(seen_offer_ids),
            "normalization_failures": sum(normalization_failures.values()),
            "expected_retailer_mismatches": expected_retailer_mismatches,
        },
        "normalization_failure_reasons": dict(sorted(normalization_failures.items())),
        "retailers": retailer_documents,
        "shadow_results": [result.summary() for result in results],
        "review_queue": {
            "queue_id": queue["queue_id"],
            "version": queue["version"],
            "checksum": queue["checksum"],
            "case_count": len(queue["cases"]),
        },
        "quality_findings": findings,
        "release_use": {
            "eligible": False,
            "reason": "Human adjudication and certification have not been completed.",
        },
    }
    document["checksum"] = _checksum(document)
    return document, queue


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile full Search evidence and construct a Matching v2 review queue."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--product-pack", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--competitor", action="append", default=[])
    parser.add_argument("--profile")
    parser.add_argument("--decided-at", required=True)
    parser.add_argument("--per-stratum-limit", type=int, default=40)
    parser.add_argument("--review-queue-version", default="1.0.0")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--pdp-archive",
        action="append",
        default=[],
        help="Raw PDP export ZIP containing manifest.json and response JSON files.",
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="CSV path, optionally prefixed with an expected retailer as retailer_id=path.",
    )
    return parser.parse_args()


def _source_argument(value: str) -> MatchingV2SourceInput:
    candidate_retailer, separator, candidate_path = value.partition("=")
    if separator and candidate_retailer and candidate_path:
        return MatchingV2SourceInput(Path(candidate_path), candidate_retailer)
    return MatchingV2SourceInput(Path(value))


def main() -> None:
    args = _arguments()
    profile, queue = build_matching_v2_evidence_profile(
        args.root,
        product_pack_id=args.product_pack,
        benchmark_retailer_id=args.benchmark,
        inputs=tuple(_source_argument(value) for value in args.input),
        decided_at=args.decided_at,
        profile_id=args.profile,
        competitor_retailer_ids=tuple(args.competitor),
        per_stratum_limit=args.per_stratum_limit,
        pdp_archives=tuple(Path(value) for value in args.pdp_archive),
        review_queue_version=args.review_queue_version,
    )
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    profile_path = output_directory / f"{args.product_pack}.evidence-profile.json"
    queue_path = output_directory / f"{args.product_pack}.review-queue.json"
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    queue_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"profile": str(profile_path), "review_queue": str(queue_path)}, indent=2))


if __name__ == "__main__":
    main()
