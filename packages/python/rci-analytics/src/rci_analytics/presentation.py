"""Deterministic, evidence-linked presentation context for analysis reports."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal
from statistics import median

from rci_analytics.matching import location_scope_key
from rci_analytics.models import ClassifiedOffer, JsonObject, MatchRecord, NormalizedOffer


def _preferred_text(values: Iterable[str | None], fallback: str) -> str:
    counts = Counter(value.strip() for value in values if value and value.strip())
    if not counts:
        return fallback
    return sorted(counts, key=lambda value: (-counts[value], value))[0]


def _money(value: Decimal) -> str:
    return f"${abs(value):,.2f}"


def _price_unit(comparison_metric: str) -> str:
    if comparison_metric == "package_price":
        return "USD/package"
    return f"USD/{comparison_metric.removeprefix('price_per_').replace('_', ' ')}"


_LABELED_UNIT_COUNT = re.compile(
    r"(?:pack\s+of\s+(\d+)|(\d+)\s*(?:count|ct|pack(?:age)?s?))",
    flags=re.IGNORECASE,
)
_WEIGHT_UNIT = re.compile(r"\b(?:lb|lbs|pounds?|oz|ounces?|kg|g)\b", flags=re.IGNORECASE)


def _labeled_unit_pack_count(title: str) -> int:
    """Return an explicit multipack count when a title also states unit weight."""

    if _WEIGHT_UNIT.search(title) is None:
        return 1
    match = _LABELED_UNIT_COUNT.search(title)
    if match is None:
        return 1
    return int(match.group(1) or match.group(2))


def _labeled_unit_packs_are_compatible(left: str, right: str) -> bool:
    return _labeled_unit_pack_count(left) == _labeled_unit_pack_count(right)


def benchmark_product_decisions(
    offers: Iterable[ClassifiedOffer],
    matches: Iterable[MatchRecord],
    *,
    benchmark_retailer: str,
    max_rows: int = 16,
    max_locations_per_row: int = 3,
    decision_rules: JsonObject | None = None,
    qa_rules: JsonObject | None = None,
) -> list[JsonObject]:
    """Build decision-first product pairs from admitted exact-match evidence.

    This is presentation context rather than a new analytical metric surface. It keeps
    product identity, outcomes, prices, and locations tied to the underlying match rows.
    """

    if max_rows < 1 or max_locations_per_row < 1:
        raise ValueError("product decision row and location limits must be positive")
    offer_index = {item.offer.offer_id: item.offer for item in offers}
    grouped: dict[
        tuple[str, str, str], list[tuple[MatchRecord, NormalizedOffer, NormalizedOffer]]
    ] = {}
    for match in matches:
        benchmark = offer_index.get(match.benchmark_offer_id)
        competitor = offer_index.get(match.competitor_offer_id)
        if benchmark is None or competitor is None or benchmark.retailer_id != benchmark_retailer:
            continue
        if not _labeled_unit_packs_are_compatible(benchmark.title, competitor.title):
            continue
        key = (
            benchmark.retailer_product_id,
            match.competitor_id,
            competitor.retailer_product_id,
        )
        grouped.setdefault(key, []).append((match, benchmark, competitor))

    rows: list[JsonObject] = []
    for (benchmark_product_id, competitor_id, competitor_product_id), values in grouped.items():
        match_rows = [value[0] for value in values]
        benchmark_offers = [value[1] for value in values]
        competitor_offers = [value[2] for value in values]
        outcomes = Counter(match.winner for match in match_rows)
        match_count = len(match_rows)
        benchmark_lower = outcomes["benchmark_lower"]
        competitor_lower = outcomes["competitor_lower"]
        parity = outcomes["parity"]
        median_gap = median(match.gap for match in match_rows)
        dominant_outcome = max(
            (
                (benchmark_lower, "benchmark_lower"),
                (competitor_lower, "competitor_lower"),
                (parity, "parity"),
            ),
            key=lambda value: (value[0], value[1] == "parity", value[1]),
        )[1]
        priority = (
            "attention"
            if dominant_outcome == "competitor_lower"
            else "protect"
            if dominant_outcome == "benchmark_lower"
            else "parity"
        )
        lead = (
            f"Competitor is {_money(median_gap)} higher at the paired median"
            if median_gap > 0
            else f"Competitor is {_money(median_gap)} lower at the paired median"
            if median_gap < 0
            else "The paired median price difference is $0.00"
        )
        geography_rows: dict[str, JsonObject] = {}
        for match, benchmark, _competitor in values:
            location_key = f"{benchmark.zipcode}|{benchmark.store_number or ''}"
            candidate: JsonObject = {
                "zipcode": benchmark.zipcode,
                "store": benchmark.store_number,
                "outcome": match.winner,
                "benchmark_price": float(match.benchmark_value),
                "competitor_price": float(match.competitor_value),
                "gap": float(match.gap),
            }
            existing = geography_rows.get(location_key)
            if existing is None or abs(float(candidate["gap"])) > abs(float(existing["gap"])):
                geography_rows[location_key] = candidate
        top_locations = sorted(
            geography_rows.values(),
            key=lambda value: (
                0 if value["outcome"] == "competitor_lower" else 1,
                -abs(float(value["gap"])),
                str(value["zipcode"]),
                str(value.get("store") or ""),
            ),
        )[:max_locations_per_row]
        seed = "|".join((benchmark_product_id, competitor_id, competitor_product_id))
        relationship_id = next(
            (
                str(match.attributes["_relationship_id"])
                for match in match_rows
                if match.attributes.get("_relationship_id")
            ),
            None,
        )
        relationship_status = next(
            (
                str(match.attributes["_relationship_status"])
                for match in match_rows
                if match.attributes.get("_relationship_status")
            ),
            "unavailable",
        )
        minimum_observations = int((decision_rules or {}).get("minimum_observations", 1))
        minimum_geographies = int((decision_rules or {}).get("minimum_geographies", 1))
        allowed_states = {
            str(value)
            for value in (decision_rules or {}).get(
                "executive_relationship_states", ["suggested", "confirmed"]
            )
        }
        suppression_reasons: list[str] = []
        if decision_rules is not None and relationship_status not in allowed_states:
            suppression_reasons.append("Relationship is not decision-ready")
        if match_count < minimum_observations:
            suppression_reasons.append(
                f"Requires at least {minimum_observations} retained observations"
            )
        if len(geography_rows) < minimum_geographies:
            suppression_reasons.append(
                f"Requires at least {minimum_geographies} retained geographies"
            )
        benchmark_median = median(match.benchmark_value for match in match_rows)
        suspicious_gap_pct = (qa_rules or {}).get("suspicious_gap_pct")
        if (
            isinstance(suspicious_gap_pct, int | float)
            and benchmark_median > 0
            and abs(median_gap / benchmark_median * 100) > Decimal(str(suspicious_gap_pct))
        ):
            suppression_reasons.append(
                "Paired median price difference exceeds the Product Pack review threshold"
            )
        qa_status = (
            "suppressed"
            if suppression_reasons
            and (decision_rules or {}).get("extreme_gap_behavior", "suppress") == "suppress"
            else "review_required"
            if suppression_reasons
            else "ready"
        )
        rows.append(
            {
                "id": f"product-{hashlib.sha256(seed.encode()).hexdigest()[:20]}",
                "relationship_id": relationship_id,
                "relationship_status": relationship_status,
                "profile_id": match_rows[0].profile_id,
                "comparison_metric": match_rows[0].comparison_metric,
                "qa_status": qa_status,
                "suppression_reasons": suppression_reasons,
                "priority": priority,
                "dominant_outcome": dominant_outcome,
                "benchmark_product_id": benchmark_product_id,
                "benchmark_product_name": _preferred_text(
                    (offer.title for offer in benchmark_offers), benchmark_product_id
                ),
                "benchmark_image_url": _preferred_text(
                    (offer.image_url for offer in benchmark_offers), ""
                )
                or None,
                "benchmark_product_url": _preferred_text(
                    (offer.product_url for offer in benchmark_offers), ""
                )
                or None,
                "competitor": competitor_id,
                "competitor_product_id": competitor_product_id,
                "competitor_product_name": _preferred_text(
                    (offer.title for offer in competitor_offers), competitor_product_id
                ),
                "competitor_image_url": _preferred_text(
                    (offer.image_url for offer in competitor_offers), ""
                )
                or None,
                "competitor_product_url": _preferred_text(
                    (offer.product_url for offer in competitor_offers), ""
                )
                or None,
                "matches": match_count,
                "geographies": len(geography_rows),
                "benchmark_lower": benchmark_lower,
                "competitor_lower": competitor_lower,
                "parity": parity,
                "benchmark_lower_share": benchmark_lower / match_count,
                "competitor_lower_share": competitor_lower / match_count,
                "median_benchmark_price": float(benchmark_median),
                "median_competitor_price": float(
                    median(match.competitor_value for match in match_rows)
                ),
                "median_gap": float(median_gap),
                "plain_insight": lead,
                "match_attributes": {
                    str(name): value
                    for name, value in match_rows[0].attributes.items()
                    if not str(name).startswith("_")
                },
                "top_locations": top_locations,
            }
        )
    ranked = sorted(
        rows,
        key=lambda row: (
            {"attention": 0, "protect": 1, "parity": 2}[str(row["priority"])],
            -float(
                row["competitor_lower_share"]
                if row["priority"] == "attention"
                else row["benchmark_lower_share"]
            ),
            -abs(float(row["median_gap"])),
            -int(row["geographies"]),
            str(row["benchmark_product_id"]),
            str(row["competitor_product_id"]),
        ),
    )
    if len(ranked) <= max_rows:
        return ranked
    attention = [row for row in ranked if row["priority"] == "attention"]
    protect = [row for row in ranked if row["priority"] == "protect"]
    parity_rows = [row for row in ranked if row["priority"] == "parity"]
    attention_limit = min(len(attention), max(1, (max_rows * 5 + 7) // 8))
    protect_limit = min(len(protect), max_rows - attention_limit)
    selected = [*attention[:attention_limit], *protect[:protect_limit]]
    selected_ids = {str(row["id"]) for row in selected}
    selected.extend(
        row
        for row in [*parity_rows, *attention[attention_limit:], *protect[protect_limit:]]
        if str(row["id"]) not in selected_ids
    )
    return selected[:max_rows]


def benchmark_product_match_candidates(
    offers: Iterable[ClassifiedOffer],
    matches: Iterable[MatchRecord],
    *,
    benchmark_retailer: str,
    profiles: Iterable[JsonObject],
    max_rows: int = 2_000,
    max_locations_per_row: int = 1,
) -> list[JsonObject]:
    """Project review candidates for every exact-geography comparison profile.

    A product relationship is emitted once per eligible profile here so the review
    service can combine identical pairs into a single governed relationship with
    deterministic lens-eligibility evidence. This projection never infers a match;
    it only annotates match rows already admitted by the Product Pack engine.
    """

    if max_rows < 1 or max_locations_per_row < 1:
        raise ValueError("product match candidate limits must be positive")
    offer_rows = list(offers)
    benchmark_footprints: dict[str, set[str]] = {}
    for classified in offer_rows:
        offer = classified.offer
        if (
            classified.in_scope
            and offer.retailer_id == benchmark_retailer
            and offer.zipcode is not None
            and offer.price is not None
            and offer.price > 0
        ):
            benchmark_footprints.setdefault(offer.retailer_product_id, set()).add(
                location_scope_key(offer)
            )
    profile_index = {
        str(profile["id"]): profile
        for profile in profiles
        if str(profile.get("geography") or "") == "exact_zip"
    }
    grouped_matches: dict[str, list[MatchRecord]] = {}
    for match in matches:
        if match.profile_id in profile_index:
            grouped_matches.setdefault(match.profile_id, []).append(match)

    candidates: list[JsonObject] = []
    for profile_id, profile in profile_index.items():
        profile_matches = grouped_matches.get(profile_id, [])
        if not profile_matches:
            continue
        comparison_metric = str(
            profile.get("comparison_metric") or profile_matches[0].comparison_metric
        )
        for row in benchmark_product_decisions(
            offer_rows,
            profile_matches,
            benchmark_retailer=benchmark_retailer,
            max_rows=max_rows,
            max_locations_per_row=max_locations_per_row,
        ):
            attributes = row.get("match_attributes", {})
            attribute_names = [
                str(name).replace("_", " ")
                for name, value in sorted(
                    attributes.items() if isinstance(attributes, dict) else []
                )
                if value is not None and str(value).strip()
            ]
            candidates.append(
                {
                    **row,
                    "profile_id": profile_id,
                    "profile_label": str(profile.get("label") or profile_id),
                    "comparison_metric": comparison_metric,
                    "match_basis": (
                        "exact_package"
                        if comparison_metric == "package_price"
                        else "normalized_unit"
                    ),
                    "match_rationale": (
                        "Product Pack attributes align on " + ", ".join(attribute_names)
                        if attribute_names
                        else "Product Pack comparison rules admitted this pair"
                    ),
                    "benchmark_location_scope_keys": sorted(
                        benchmark_footprints.get(str(row["benchmark_product_id"]), set())
                    ),
                }
            )

    return sorted(
        candidates,
        key=lambda row: (
            str(row["competitor"]),
            str(row["benchmark_product_id"]),
            str(row["competitor_product_id"]),
            str(row["profile_id"]),
        ),
    )[:max_rows]


def benchmark_product_evidence(
    offers: Iterable[ClassifiedOffer],
    decisions: Iterable[JsonObject],
    *,
    benchmark_retailer: str,
    parity_tolerance: Decimal = Decimal("0.01"),
) -> dict[str, JsonObject]:
    """Build store-grain evidence for the product pairs shown in a report.

    Search observations remain authoritative for price and location. For an exact-ZIP
    product pair, every distinct benchmark store observation is compared with the
    lowest observed price for that exact competitor product in the same ZIP. This is
    deliberately separate from the analytical match metric, which retains one lowest
    qualifying offer per ZIP and configured attribute set.
    """

    decision_rows = [dict(value) for value in decisions]
    selected_products = {
        (benchmark_retailer, str(row["benchmark_product_id"])) for row in decision_rows
    } | {(str(row["competitor"]), str(row["competitor_product_id"])) for row in decision_rows}
    observations: dict[tuple[str, str], list[ClassifiedOffer]] = {}
    for classified in offers:
        offer = classified.offer
        key = (offer.retailer_id, offer.retailer_product_id)
        if (
            classified.in_scope
            and key in selected_products
            and offer.price is not None
            and offer.price > 0
            and offer.zipcode
        ):
            observations.setdefault(key, []).append(classified)

    evidence: dict[str, JsonObject] = {}
    for decision in decision_rows:
        decision_id = str(decision["id"])
        competitor_id = str(decision["competitor"])
        comparison_metric = str(decision.get("comparison_metric") or "package_price")
        comparison_unit = _price_unit(comparison_metric)
        benchmark_key = (benchmark_retailer, str(decision["benchmark_product_id"]))
        competitor_key = (competitor_id, str(decision["competitor_product_id"]))
        benchmark_locations = _lowest_store_observations(
            observations.get(benchmark_key, []), comparison_metric=comparison_metric
        )
        competitor_locations = _lowest_store_observations(
            observations.get(competitor_key, []), comparison_metric=comparison_metric
        )
        competitor_by_zip: dict[str, ClassifiedOffer] = {}
        for classified in competitor_locations.values():
            offer = classified.offer
            previous = competitor_by_zip.get(str(offer.zipcode))
            value = _comparison_value(classified, comparison_metric)
            previous_value = (
                _comparison_value(previous, comparison_metric) if previous is not None else None
            )
            if value is not None and (
                previous is None
                or previous_value is None
                or (value, offer.offer_id) < (previous_value, previous.offer.offer_id)
            ):
                competitor_by_zip[str(offer.zipcode)] = classified

        rows: list[JsonObject] = []
        for benchmark_classified in benchmark_locations.values():
            benchmark = benchmark_classified.offer
            competitor_classified = competitor_by_zip.get(str(benchmark.zipcode))
            if competitor_classified is None:
                continue
            competitor = competitor_classified.offer
            if benchmark.price is None or competitor.price is None:
                continue
            benchmark_value = _comparison_value(benchmark_classified, comparison_metric)
            competitor_value = _comparison_value(competitor_classified, comparison_metric)
            if benchmark_value is None or competitor_value is None:
                continue
            comparison_gap = competitor_value - benchmark_value
            package_gap = competitor.price - benchmark.price
            outcome = (
                "parity"
                if abs(comparison_gap) <= parity_tolerance
                else "benchmark_lower"
                if comparison_gap > 0
                else "competitor_lower"
            )
            row_seed = "|".join(
                (
                    decision_id,
                    str(benchmark.zipcode),
                    benchmark.store_number or benchmark.offer_id,
                    competitor.store_number or competitor.offer_id,
                )
            )
            rows.append(
                {
                    "id": f"evidence-{hashlib.sha256(row_seed.encode()).hexdigest()[:24]}",
                    "decision_id": decision_id,
                    "comparison_basis": (
                        f"{comparison_metric} for benchmark store vs lowest observed exact "
                        "competitor product in the same ZIP"
                    ),
                    "comparison_metric": comparison_metric,
                    "comparison_unit": comparison_unit,
                    "raw_price_unit": "USD/package",
                    "zipcode": benchmark.zipcode,
                    "outcome": outcome,
                    "benchmark_retailer": benchmark_retailer,
                    "benchmark_product_id": benchmark.retailer_product_id,
                    "benchmark_product_name": benchmark.title,
                    "benchmark_store": benchmark.store_number,
                    "benchmark_price": float(benchmark.price),
                    "benchmark_comparison_value": float(benchmark_value),
                    "benchmark_latitude": benchmark.latitude,
                    "benchmark_longitude": benchmark.longitude,
                    "competitor": competitor_id,
                    "competitor_product_id": competitor.retailer_product_id,
                    "competitor_product_name": competitor.title,
                    "competitor_store": competitor.store_number,
                    "competitor_price": float(competitor.price),
                    "competitor_comparison_value": float(competitor_value),
                    "competitor_minus_benchmark": float(package_gap),
                    "comparison_gap": float(comparison_gap),
                }
            )
        rows.sort(
            key=lambda row: (
                {"competitor_lower": 0, "benchmark_lower": 1, "parity": 2}[str(row["outcome"])],
                -abs(float(row["comparison_gap"])),
                str(row["zipcode"]),
                str(row.get("benchmark_store") or ""),
            )
        )
        outcomes = Counter(str(row["outcome"]) for row in rows)
        matched_zips = {str(row["zipcode"]) for row in rows}
        matched_competitor_stores = {
            (str(row["zipcode"]), str(row.get("competitor_store") or "ZIP-level")) for row in rows
        }
        evidence[decision_id] = {
            "decision_id": decision_id,
            "comparison_grain": (
                f"one row per observed benchmark store; exact product pair; same ZIP; "
                f"outcomes use {comparison_metric}"
            ),
            "comparison_metric": comparison_metric,
            "comparison_unit": comparison_unit,
            "raw_price_unit": "USD/package",
            "price_source": "retailer search observation",
            "attribute_source": "Product Pack classification with PDP enrichment when available",
            "summary": {
                "matched_zip_markets": len(matched_zips),
                "benchmark_store_observations": len(rows),
                "competitor_store_observations": len(matched_competitor_stores),
                "benchmark_stores_lower": outcomes["benchmark_lower"],
                "benchmark_stores_undercut": outcomes["competitor_lower"],
                "price_parity": outcomes["parity"],
            },
            "rows": rows,
        }
    return evidence


def merge_product_evidence_summary(
    decisions: Iterable[JsonObject], evidence: dict[str, JsonObject]
) -> list[JsonObject]:
    """Attach bounded evidence summaries without embedding store rows in report views."""

    merged: list[JsonObject] = []
    for source in decisions:
        row = dict(source)
        item = evidence.get(str(row.get("id", "")))
        if item is not None:
            row["evidence_summary"] = dict(item.get("summary", {}))
            row["comparison_grain"] = item.get("comparison_grain")
            row["evidence_available"] = True
        merged.append(row)
    return merged


def _comparison_value(
    classified: ClassifiedOffer,
    comparison_metric: str,
) -> Decimal | None:
    value = (
        classified.offer.price
        if comparison_metric == "package_price"
        else classified.metrics.get(comparison_metric)
    )
    return value if value is not None and value > 0 else None


def _lowest_store_observations(
    offers: Iterable[ClassifiedOffer],
    *,
    comparison_metric: str,
) -> dict[tuple[str, str], ClassifiedOffer]:
    selected: dict[tuple[str, str], ClassifiedOffer] = {}
    for classified in offers:
        offer = classified.offer
        value = _comparison_value(classified, comparison_metric)
        if not offer.zipcode or offer.price is None or offer.price <= 0:
            continue
        if value is None:
            continue
        location = offer.store_number or "ZIP-level"
        key = (offer.zipcode, location)
        previous = selected.get(key)
        previous_value = (
            _comparison_value(previous, comparison_metric) if previous is not None else None
        )
        if (
            previous is None
            or previous_value is None
            or (value, offer.offer_id)
            < (
                previous_value,
                previous.offer.offer_id,
            )
        ):
            selected[key] = classified
    return selected


def merge_product_decision_context(
    decisions: Iterable[JsonObject],
    product_context: Iterable[JsonObject],
    *,
    benchmark_retailer: str,
) -> list[JsonObject]:
    """Overlay PDP-backed identity fields without changing price-decision evidence."""

    context_index = {
        str(item.get("canonical_product_id")): item
        for item in product_context
        if item.get("canonical_product_id")
    }
    merged: list[JsonObject] = []
    for source in decisions:
        row = dict(source)
        for prefix, retailer, product_id in (
            (
                "benchmark",
                benchmark_retailer,
                str(row.get("benchmark_product_id", "")),
            ),
            (
                "competitor",
                str(row.get("competitor", "")),
                str(row.get("competitor_product_id", "")),
            ),
        ):
            context = context_index.get(f"{retailer}:{product_id}")
            if context is None:
                continue
            for target, source_name in (
                (f"{prefix}_product_name", "name"),
                (f"{prefix}_image_url", "image_url"),
                (f"{prefix}_product_url", "url"),
                (f"{prefix}_brand", "brand"),
                (f"{prefix}_description", "description"),
                (f"{prefix}_category_path", "category_path"),
                (f"{prefix}_identifiers", "identifiers"),
                (f"{prefix}_specification", "specification"),
                (f"{prefix}_physical_properties", "physical_properties"),
                (f"{prefix}_variant_configuration", "variant_configuration"),
            ):
                value = context.get(source_name)
                if value not in (None, "", {}, []):
                    row[target] = value
        merged.append(row)
    return merged


def _sample_geographies(rows: list[JsonObject], limit: int) -> list[JsonObject]:
    """Select a stable, geographically distributed sample for browser-safe maps."""

    ordered = sorted(
        rows,
        key=lambda row: (
            float(row["longitude"]),
            float(row["latitude"]),
            str(row["id"]),
        ),
    )
    if len(ordered) <= limit:
        return ordered
    return [ordered[(index * len(ordered)) // limit] for index in range(limit)]


def benchmark_product_map_points(
    offers: Iterable[ClassifiedOffer],
    matches: Iterable[MatchRecord],
    *,
    benchmark_retailer: str,
    max_products: int = 20,
    max_points_per_product: int = 150,
    allowed_relationship_ids: set[str] | None = None,
) -> list[JsonObject]:
    """Project exact-match evidence into a benchmark-product-filterable map dataset."""

    if max_products < 1 or max_points_per_product < 1:
        raise ValueError("map Product and point limits must be positive")
    offer_index = {item.offer.offer_id: item for item in offers}
    candidate_rows: list[JsonObject] = []
    product_counts: Counter[str] = Counter()
    for match in matches:
        relationship_id = str(match.attributes.get("_relationship_id") or "")
        if allowed_relationship_ids is not None and relationship_id not in allowed_relationship_ids:
            continue
        benchmark = offer_index.get(match.benchmark_offer_id)
        competitor = offer_index.get(match.competitor_offer_id)
        if benchmark is None or benchmark.offer.retailer_id != benchmark_retailer:
            continue
        if competitor is not None and not _labeled_unit_packs_are_compatible(
            benchmark.offer.title, competitor.offer.title
        ):
            continue
        offer = benchmark.offer
        if offer.latitude is None or offer.longitude is None:
            continue
        product_id = offer.retailer_product_id
        point_seed = "|".join(
            (
                match.profile_id,
                match.competitor_id,
                product_id,
                match.geography_key,
                offer.offer_id,
            )
        )
        point_id = hashlib.sha256(point_seed.encode()).hexdigest()[:24]
        gap = float(match.gap)
        outcome_label = {
            "benchmark_lower": "Benchmark lower",
            "competitor_lower": "Competitor lower",
            "parity": "Price parity",
        }.get(match.winner, match.winner.replace("_", " ").title())
        candidate_rows.append(
            {
                "id": point_id,
                "label": offer.title,
                "latitude": offer.latitude,
                "longitude": offer.longitude,
                "value": gap,
                "value_label": (
                    f"{outcome_label} · paired difference ${abs(gap):.2f} "
                    f"{_price_unit(match.comparison_metric).removeprefix('USD')}"
                ),
                "retailer": benchmark_retailer,
                "relationship_id": relationship_id or None,
                "profile_id": match.profile_id,
                "comparison_metric": match.comparison_metric,
                "benchmark_product_id": product_id,
                "benchmark_product_name": offer.title,
                "competitor": match.competitor_id,
                "outcome": match.winner,
                "zipcode": offer.zipcode,
                "store": offer.store_number,
                "benchmark_price": float(match.benchmark_value),
                "competitor_price": float(match.competitor_value),
                "matches": 1,
            }
        )
        product_counts[product_id] += 1
    selected_products = {
        product_id
        for product_id, _count in sorted(
            product_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:max_products]
    }
    by_product: dict[str, list[JsonObject]] = {product_id: [] for product_id in selected_products}
    for row in candidate_rows:
        product_id = str(row["benchmark_product_id"])
        if product_id in by_product:
            by_product[product_id].append(row)
    return [
        row
        for product_id in sorted(
            by_product,
            key=lambda value: (-product_counts[value], value),
        )
        for row in _sample_geographies(by_product[product_id], max_points_per_product)
    ]
