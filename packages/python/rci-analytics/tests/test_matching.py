from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import (
    ComparisonEngine,
    ComparisonInputReducer,
    RelationshipInputReducer,
    geographic_overlap,
    product_footprint,
    resolve_one_to_one_relationships,
)
from rci_analytics.models import ProductMatchRule
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.product_pack import ProductPackLoader

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _pipeline():
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    document = copy.deepcopy(pack.document)
    document.pop("retailer_overrides")
    for attribute in document["attributes"]:
        if attribute["name"] == "organic":
            attribute["extraction_rules"][0]["false_terms"] = [
                "conventional",
                "non organic",
            ]
        if attribute["name"] == "specialty_claim":
            attribute["extraction_rules"][0]["values"]["None"] = ["standard"]
    pack = replace(pack, document=document)
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config" / "retailer-catalog.json")
    )
    return normalizer, OfferClassifier(pack), ComparisonEngine(pack)


def _row(
    retailer_id: str,
    product_id: str,
    title: str,
    price: str,
    *,
    zipcode: str = "10001",
    store: str = "store-1",
    latitude: float = 40.7500,
    longitude: float = -73.9900,
) -> dict[str, object]:
    governed_title = (
        f"{title} Standard" if "organic" in title.casefold() else f"{title} Conventional Standard"
    )
    return {
        "retailer_id": retailer_id,
        "retailer_product_id": product_id,
        "title": governed_title,
        "price": price,
        "zipcode": zipcode,
        "store_number": store,
        "stock_availability": True,
        "latitude": latitude,
        "longitude": longitude,
    }


def _classified():
    normalizer, classifier, engine = _pipeline()
    rows = [
        _row("walmart_us", "w-1", "Fresh Strawberries, 1 lb", "2.38"),
        _row("walmart_us", "w-2", "Fresh Strawberries, 2 lb", "4.52"),
        _row("walmart_us", "w-o", "Fresh Organic Strawberries, 1 lb", "3.33"),
        _row("aldi_us", "a-1", "Fresh Strawberries, 1 lb", "2.55"),
        _row("aldi_us", "a-2", "Fresh Strawberries, 2 lb", "5.99"),
        _row("aldi_us", "a-o", "Fresh Organic Strawberries, 1 lb", "3.85"),
        _row("amazon_us_same_day", "m-1", "Strawberries, 1 lb", "1.99"),
        _row("amazon_us_same_day", "m-2", "Strawberries, 2 lb", "5.32"),
        _row("amazon_us_same_day", "m-o", "Organic Strawberries, 1 lb", "3.34"),
    ]
    offers = classifier.classify_many(normalizer.normalize_many(rows))
    return offers, engine


def test_strict_profile_never_crosses_package_weights() -> None:
    offers, engine = _classified()
    assert engine.comparison_metric("strict") == "package_price"
    assert engine.comparison_metric("unit_price") == "price_per_lb"
    matches = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="strict",
    )

    assert len(matches) == 3
    assert {(match.attributes["weight_oz"], match.winner) for match in matches} == {
        (16.0, "competitor_lower"),
        (16.0, "parity"),
        (32.0, "benchmark_lower"),
    }
    assert all(match.comparison_metric == "package_price" for match in matches)


def test_exact_package_profile_separates_variable_weight_from_fixed_package() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    document = copy.deepcopy(pack.document)
    package_format = next(
        attribute for attribute in document["attributes"] if attribute["name"] == "package_format"
    )
    package_format.update(
        {
            "role": "matching",
            "required_for_strict": True,
            "unknown_policy": "reject_strict",
            "allowed_values": [
                "standard",
                "roll_or_chub",
                "tray_or_value_pack",
                "multipack",
                "variable_weight",
            ],
        }
    )
    package_format["extraction_rules"][0]["values"]["variable_weight"] = [
        "per lb",
        "per pound",
    ]
    strict = next(profile for profile in document["matching_profiles"] if profile["id"] == "strict")
    strict["dimensions"].append("package_format")
    pack = replace(pack, document=document)
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config" / "retailer-catalog.json")
    )
    classifier = OfferClassifier(pack)
    engine = ComparisonEngine(pack)
    rows = [
        {
            "retailer_id": "walmart_us",
            "retailer_product_id": "15136795",
            "title": "73% Lean / 27% Fat Ground Beef, 5 lb Roll, Fresh",
            "url": "https://www.walmart.com/ip/ground-beef/15136795",
            "price": "24.94",
            "zipcode": "71111",
            "store_number": "1",
        },
        {
            "retailer_id": "aldi_us",
            "retailer_product_id": "17499083",
            "title": "73% Lean 27% Fat Ground Beef",
            "url": ("https://www.aldi.us/store/aldi/products/17499083-ground-beef-chub-5-lb"),
            "price": "14.39",
            "zipcode": "71111",
            "store_number": "475-107",
        },
        {
            "retailer_id": "aldi_us",
            "retailer_product_id": "19119422",
            "title": "USDA 73% Lean 27% Fat Ground Beef, per lb",
            "url": "https://www.aldi.us/store/aldi/products/19119422-ground-beef-per-lb",
            "price": "25.95",
            "zipcode": "71111",
            "store_number": "475-107",
        },
    ]
    offers = classifier.classify_many(normalizer.normalize_many(rows))
    by_product = {offer.offer.retailer_product_id: offer for offer in offers}
    assert by_product["15136795"].attributes["package_format"] == "roll_or_chub"
    assert by_product["17499083"].attributes["package_format"] == "roll_or_chub"
    assert by_product["19119422"].attributes["package_format"] == "variable_weight"

    relationship_reducer = RelationshipInputReducer(
        pack,
        profile_ids={"strict", "unit_price"},
    )
    relationship_reducer.extend(offers)
    relationship_offers = relationship_reducer.offers()
    offer_products = {
        offer.offer.offer_id: offer.offer.retailer_product_id for offer in relationship_offers
    }
    strict_pairs = {
        (
            offer_products[match.benchmark_offer_id],
            offer_products[match.competitor_offer_id],
        )
        for match in engine.compare_products(
            relationship_offers,
            benchmark_id="walmart_us",
            competitor_id="aldi_us",
            profile_id="strict",
        )
    }
    unit_pairs = {
        (
            offer_products[match.benchmark_offer_id],
            offer_products[match.competitor_offer_id],
        )
        for match in engine.compare_products(
            relationship_offers,
            benchmark_id="walmart_us",
            competitor_id="aldi_us",
            profile_id="unit_price",
        )
    }

    assert strict_pairs == {("15136795", "17499083")}
    assert unit_pairs == {
        ("15136795", "17499083"),
        ("15136795", "19119422"),
    }


def test_unit_price_profile_selects_lowest_positive_price_per_lb() -> None:
    offers, engine = _classified()
    aldi = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="unit_price",
    )
    amazon = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="unit_price",
    )

    aldi_by_organic = {match.attributes["organic"]: match for match in aldi}
    amazon_by_organic = {match.attributes["organic"]: match for match in amazon}
    assert aldi_by_organic[False].benchmark_value == Decimal("2.26")
    assert aldi_by_organic[False].competitor_value == Decimal("2.55")
    assert aldi_by_organic[False].gap == Decimal("0.29")
    assert amazon_by_organic[False].benchmark_value == Decimal("2.26")
    assert amazon_by_organic[False].competitor_value == Decimal("1.99")
    assert amazon_by_organic[False].gap == Decimal("-0.27")
    assert amazon_by_organic[True].winner == "parity"
    assert all(match.comparison_metric == "price_per_lb" for match in [*aldi, *amazon])


def test_governed_confirmation_replaces_conflicting_automatic_pairs() -> None:
    offers, engine = _classified()

    matches = engine.compare_governed(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
        rules=[
            ProductMatchRule(
                competitor_id="aldi_us",
                profile_id="strict",
                benchmark_product_id="w-1",
                competitor_product_id="a-2",
                decision="confirmed",
            )
        ],
    )
    product_ids = {item.offer.offer_id: item.offer.retailer_product_id for item in offers}
    product_pairs = {
        (product_ids[match.benchmark_offer_id], product_ids[match.competitor_offer_id])
        for match in matches
    }

    assert len(matches) == 2
    assert any(match.attributes.get("_match_origin") == "user_confirmed" for match in matches)
    assert product_pairs == {("w-1", "a-2"), ("w-o", "a-o")}


def test_governed_relationship_applies_to_every_eligible_profile() -> None:
    offers, engine = _classified()
    rule = ProductMatchRule(
        competitor_id="aldi_us",
        profile_id="strict",
        benchmark_product_id="w-1",
        competitor_product_id="a-2",
        decision="confirmed",
        eligible_profile_ids=("strict", "unit_price"),
    )

    matches = engine.compare_governed(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="unit_price",
        rules=[rule],
    )

    assert any(match.attributes.get("_match_origin") == "user_confirmed" for match in matches)


def test_governed_rejection_removes_only_the_rejected_pair() -> None:
    offers, engine = _classified()

    matches = engine.compare_governed(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
        rules=[
            ProductMatchRule(
                competitor_id="aldi_us",
                profile_id="strict",
                benchmark_product_id="w-1",
                competitor_product_id="a-1",
                decision="rejected",
            )
        ],
    )

    assert len(matches) == 2


def test_governed_rules_fail_closed_when_not_one_to_one() -> None:
    offers, engine = _classified()
    rules = [
        ProductMatchRule("aldi_us", "strict", "w-1", "a-1", "confirmed"),
        ProductMatchRule("aldi_us", "strict", "w-1", "a-2", "confirmed"),
    ]

    with pytest.raises(ValueError, match="one-to-one"):
        engine.compare_governed(
            offers,
            benchmark_id="walmart_us",
            competitor_id="aldi_us",
            profile_id="strict",
            rules=rules,
        )


def test_scoped_relationships_allow_reuse_only_across_disjoint_store_footprints() -> None:
    normalizer, classifier, engine = _pipeline()
    offers = classifier.classify_many(
        normalizer.normalize_many(
            [
                _row(
                    "walmart_us",
                    "w-regional-north",
                    "Fresh Strawberries, 1 lb",
                    "2.38",
                    zipcode="10001",
                    store="w-1",
                ),
                _row(
                    "walmart_us",
                    "w-regional-south",
                    "Fresh Strawberries, 1 lb",
                    "2.48",
                    zipcode="10002",
                    store="w-2",
                ),
                _row(
                    "aldi_us",
                    "a-private-label",
                    "Fresh Strawberries, 1 lb",
                    "2.29",
                    zipcode="10001",
                    store="a-1",
                ),
                _row(
                    "aldi_us",
                    "a-private-label",
                    "Fresh Strawberries, 1 lb",
                    "2.39",
                    zipcode="10002",
                    store="a-2",
                ),
            ]
        )
    )
    rules = [
        ProductMatchRule(
            "aldi_us",
            "strict",
            "w-regional-north",
            "a-private-label",
            "confirmed",
            comparison_family_key="conventional_1lb",
            scope_mode="explicit_benchmark_locations",
            scope_definition={"benchmark_location_scope_keys": ["walmart_us|10001|w-1"]},
        ),
        ProductMatchRule(
            "aldi_us",
            "strict",
            "w-regional-south",
            "a-private-label",
            "confirmed",
            comparison_family_key="conventional_1lb",
            scope_mode="explicit_benchmark_locations",
            scope_definition={"benchmark_location_scope_keys": ["walmart_us|10002|w-2"]},
        ),
    ]

    matches = engine.compare_governed(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
        rules=rules,
    )

    assert [match.geography_key for match in matches] == [
        "walmart_us|10001|w-1",
        "walmart_us|10002|w-2",
    ]
    assert all(
        match.attributes["_comparison_family_key"] == "conventional_1lb" for match in matches
    )


def test_scoped_relationships_fail_closed_when_primary_scopes_overlap() -> None:
    offers, engine = _classified()
    scope = {"benchmark_location_scope_keys": ["walmart_us|10001|store-1"]}
    rules = [
        ProductMatchRule(
            "aldi_us",
            "strict",
            "w-1",
            "a-1",
            "confirmed",
            scope_mode="explicit_benchmark_locations",
            scope_definition=scope,
        ),
        ProductMatchRule(
            "aldi_us",
            "strict",
            "w-1",
            "a-2",
            "confirmed",
            scope_mode="explicit_benchmark_locations",
            scope_definition=scope,
        ),
    ]

    with pytest.raises(ValueError, match="benchmark location context"):
        engine.compare_governed(
            offers,
            benchmark_id="walmart_us",
            competitor_id="aldi_us",
            profile_id="strict",
            rules=rules,
        )


def test_certified_product_footprints_allow_many_to_one_relationship_evidence() -> None:
    offers, engine = _classified()
    rules = [
        ProductMatchRule(
            "aldi_us",
            "strict",
            "w-1",
            "a-1",
            "confirmed",
            scope_mode="observed_benchmark_product_footprint",
        ),
        ProductMatchRule(
            "aldi_us",
            "strict",
            "w-o",
            "a-1",
            "confirmed",
            scope_mode="observed_benchmark_product_footprint",
        ),
    ]

    matches = engine.compare_governed(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
        rules=rules,
        allow_automatic=False,
    )
    resolution = resolve_one_to_one_relationships(
        offers,
        matches,
        benchmark_retailer="walmart_us",
        profile_priority=("strict",),
    )

    assert len(resolution.matches) == 2
    assert {
        (str(row["benchmark_product_id"]), str(row["competitor_product_id"]))
        for row in resolution.relationships
    } == {("w-1", "a-1"), ("w-o", "a-1")}
    assert all(row["status"] == "confirmed" for row in resolution.relationships)


def test_product_footprint_uses_positive_search_observations_at_store_grain() -> None:
    offers, _engine = _classified()

    footprint = product_footprint(
        offers,
        analysis_id="analysis-strawberries",
        retailer_id="walmart_us",
        product_id="w-1",
    )

    assert footprint["source_authority"] == "search"
    assert footprint["locations"] == [
        {
            "scope_key": "walmart_us|10001|store-1",
            "store_number": "store-1",
            "zipcode": "10001",
            "state": None,
            "latitude": 40.75,
            "longitude": -73.99,
            "observations": 1,
            "lowest_positive_price": 2.38,
        }
    ]


def test_automatic_relationships_are_one_to_one_across_lenses() -> None:
    offers, engine = _classified()
    matches = [
        match
        for profile_id in ("strict", "unit_price")
        for match in engine.compare(
            offers,
            benchmark_id="walmart_us",
            competitor_id="aldi_us",
            profile_id=profile_id,
        )
    ]

    resolution = resolve_one_to_one_relationships(
        offers,
        matches,
        benchmark_retailer="walmart_us",
        profile_priority=("strict", "unit_price"),
    )

    benchmark_ids = [str(row["benchmark_product_id"]) for row in resolution.relationships]
    competitor_ids = [str(row["competitor_product_id"]) for row in resolution.relationships]
    assert len(benchmark_ids) == len(set(benchmark_ids))
    assert len(competitor_ids) == len(set(competitor_ids))
    assert all(row["status"] == "suggested" for row in resolution.relationships)
    assert all(match.attributes.get("_relationship_id") for match in resolution.matches)


def test_equally_valid_many_to_one_candidates_remain_ambiguous() -> None:
    offers, engine = _classified()
    strict = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
    )
    first = next(match for match in strict if match.attributes["weight_oz"] == 16.0)
    benchmark_two_pound = next(
        item.offer.offer_id
        for item in offers
        if item.offer.retailer_id == "walmart_us" and item.offer.retailer_product_id == "w-2"
    )
    candidates = [
        first,
        replace(
            first,
            geography_key="10002",
            benchmark_offer_id=benchmark_two_pound,
        ),
    ]

    resolution = resolve_one_to_one_relationships(
        offers,
        candidates,
        benchmark_retailer="walmart_us",
        profile_priority=("strict",),
    )

    assert resolution.matches == ()
    assert resolution.relationships == ()
    assert len(resolution.ambiguous_groups) == 1
    assert len(resolution.ambiguous_groups[0]["candidates"]) == 2


def test_automatic_scoped_relationships_reuse_product_across_disjoint_footprints() -> None:
    normalizer, classifier, engine = _pipeline()
    offers = classifier.classify_many(
        normalizer.normalize_many(
            [
                _row(
                    "walmart_us",
                    "w-regional-north",
                    "Fresh Strawberries, 1 lb",
                    "2.38",
                    zipcode="10001",
                    store="w-1",
                ),
                _row(
                    "walmart_us",
                    "w-regional-south",
                    "Fresh Strawberries, 1 lb",
                    "2.48",
                    zipcode="10002",
                    store="w-2",
                ),
                _row(
                    "aldi_us",
                    "a-private-label",
                    "Fresh Strawberries, 1 lb",
                    "2.29",
                    zipcode="10001",
                    store="a-1",
                ),
                _row(
                    "aldi_us",
                    "a-private-label",
                    "Fresh Strawberries, 1 lb",
                    "2.39",
                    zipcode="10002",
                    store="a-2",
                ),
            ]
        )
    )
    candidates = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
    )

    resolution = resolve_one_to_one_relationships(
        offers,
        candidates,
        benchmark_retailer="walmart_us",
        profile_priority=("strict",),
        profile_scope_policies={
            "strict": {
                "default_scope_mode": "observed_benchmark_product_footprint",
                "allow_scoped_reuse": True,
                "comparison_context_grain": "benchmark_location",
                "minimum_locations": 1,
            }
        },
    )

    assert {
        (str(row["benchmark_product_id"]), str(row["competitor_product_id"]))
        for row in resolution.relationships
    } == {
        ("w-regional-north", "a-private-label"),
        ("w-regional-south", "a-private-label"),
    }
    assert {tuple(row["benchmark_location_scope_keys"]) for row in resolution.relationships} == {
        ("walmart_us|10001|w-1",),
        ("walmart_us|10002|w-2",),
    }
    assert all(
        row["scope_mode"] == "observed_benchmark_product_footprint"
        for row in resolution.relationships
    )


def test_automatic_scoped_relationships_exclude_ambiguous_overlapping_footprints() -> None:
    normalizer, classifier, engine = _pipeline()
    offers = classifier.classify_many(
        normalizer.normalize_many(
            [
                _row(
                    "walmart_us",
                    "w-regional-north",
                    "Fresh Strawberries, 1 lb",
                    "2.38",
                    zipcode="10001",
                    store="w-1",
                ),
                _row(
                    "walmart_us",
                    "w-regional-north",
                    "Fresh Strawberries, 1 lb",
                    "2.58",
                    zipcode="10002",
                    store="w-2",
                ),
                _row(
                    "walmart_us",
                    "w-regional-south",
                    "Fresh Strawberries, 1 lb",
                    "2.48",
                    zipcode="10002",
                    store="w-2",
                ),
                _row(
                    "aldi_us",
                    "a-private-label",
                    "Fresh Strawberries, 1 lb",
                    "2.29",
                    zipcode="10001",
                    store="a-1",
                ),
                _row(
                    "aldi_us",
                    "a-private-label",
                    "Fresh Strawberries, 1 lb",
                    "2.39",
                    zipcode="10002",
                    store="a-2",
                ),
            ]
        )
    )
    candidates = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
    )

    resolution = resolve_one_to_one_relationships(
        offers,
        candidates,
        benchmark_retailer="walmart_us",
        profile_priority=("strict",),
        profile_scope_policies={
            "strict": {
                "default_scope_mode": "observed_benchmark_product_footprint",
                "allow_scoped_reuse": True,
                "comparison_context_grain": "benchmark_location",
                "minimum_locations": 1,
            }
        },
    )

    assert resolution.matches == ()
    assert resolution.relationships == ()
    assert len(resolution.ambiguous_groups) == 1
    assert len(resolution.ambiguous_groups[0]["candidates"]) == 2


def test_confirmed_relationship_wins_before_automatic_resolution() -> None:
    offers, engine = _classified()
    rule = ProductMatchRule(
        competitor_id="aldi_us",
        profile_id="strict",
        benchmark_product_id="w-1",
        competitor_product_id="a-2",
        decision="confirmed",
        eligible_profile_ids=("strict", "unit_price"),
    )
    matches = [
        match
        for profile_id in ("strict", "unit_price")
        for match in engine.compare_governed(
            offers,
            benchmark_id="walmart_us",
            competitor_id="aldi_us",
            profile_id=profile_id,
            rules=(rule,),
        )
    ]

    resolution = resolve_one_to_one_relationships(
        offers,
        matches,
        benchmark_retailer="walmart_us",
        profile_priority=("strict", "unit_price"),
    )

    confirmed = next(row for row in resolution.relationships if row["status"] == "confirmed")
    assert confirmed["benchmark_product_id"] == "w-1"
    assert confirmed["competitor_product_id"] == "a-2"
    assert confirmed["eligible_profile_ids"] == ["strict", "unit_price"]


def test_geographic_overlap_and_optional_radius_validation() -> None:
    normalizer, classifier, engine = _pipeline()
    rows = [
        _row(
            "walmart_us",
            "w-near",
            "Fresh Strawberries, 1 lb",
            "2.38",
            store="w-near",
            latitude=41.881832,
            longitude=-87.623177,
        ),
        _row(
            "aldi_us",
            "a-near",
            "Fresh Strawberries, 1 lb",
            "2.55",
            store="a-near",
            latitude=41.889,
            longitude=-87.630,
        ),
        _row(
            "aldi_us",
            "a-far",
            "Fresh Strawberries, 1 lb",
            "2.55",
            zipcode="60660",
            store="a-far",
            latitude=42.2,
            longitude=-88.2,
        ),
    ]
    offers = classifier.classify_many(normalizer.normalize_many(rows))

    assert geographic_overlap(offers, "walmart_us", "aldi_us") == {"10001"}
    matches = engine.compare(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="aldi_10mi",
    )
    assert len(matches) == 1
    assert matches[0].winner == "benchmark_lower"
    assert matches[0].distance_miles is not None
    assert matches[0].distance_miles < 10


def test_streaming_reducer_preserves_generic_profile_results() -> None:
    offers, engine = _classified()
    reducer = ComparisonInputReducer(engine.pack)
    reducer.extend(offers)
    retained = reducer.offers()

    for competitor_id in ("aldi_us", "amazon_us_same_day"):
        for profile_id in ("strict", "unit_price"):
            expected = engine.compare(
                offers,
                benchmark_id="walmart_us",
                competitor_id=competitor_id,
                profile_id=profile_id,
            )
            actual = engine.compare(
                retained,
                benchmark_id="walmart_us",
                competitor_id=competitor_id,
                profile_id=profile_id,
            )
            assert actual == expected

    assert reducer.input_offers == len(offers)
    assert reducer.retained_offers <= len(offers)


def test_relationship_resolution_uses_complete_product_footprints() -> None:
    normalizer, classifier, engine = _pipeline()
    offers = classifier.classify_many(
        normalizer.normalize_many(
            [
                _row(
                    "walmart_us",
                    "w-1",
                    "Fresh Organic Strawberries, 1 lb",
                    "2.00",
                    zipcode="10001",
                    store="w-a",
                ),
                _row(
                    "walmart_us",
                    "w-1",
                    "Fresh Organic Strawberries, 1 lb",
                    "4.00",
                    zipcode="20002",
                    store="w-b",
                ),
                _row(
                    "walmart_us",
                    "w-2",
                    "Fresh Organic Strawberries, 1 lb",
                    "4.00",
                    zipcode="10001",
                    store="w-a",
                ),
                _row(
                    "walmart_us",
                    "w-2",
                    "Fresh Organic Strawberries, 1 lb",
                    "2.00",
                    zipcode="20002",
                    store="w-b",
                ),
                _row(
                    "aldi_us",
                    "a-1",
                    "Fresh Organic Strawberries, 1 lb",
                    "3.00",
                    zipcode="10001",
                    store="a-a",
                ),
                _row(
                    "aldi_us",
                    "a-1",
                    "Fresh Organic Strawberries, 1 lb",
                    "3.00",
                    zipcode="20002",
                    store="a-b",
                ),
            ]
        )
    )
    relationship_reducer = RelationshipInputReducer(engine.pack, profile_ids={"strict"})
    relationship_reducer.extend(offers)
    relationship_offers = relationship_reducer.offers()
    candidates = engine.compare_products(
        relationship_offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
    )

    resolution = resolve_one_to_one_relationships(
        relationship_offers,
        candidates,
        benchmark_retailer="walmart_us",
        profile_priority=("strict",),
        profile_scope_policies={
            "strict": {
                "default_scope_mode": "observed_benchmark_product_footprint",
                "allow_scoped_reuse": True,
                "comparison_context_grain": "benchmark_location",
                "minimum_locations": 1,
            }
        },
    )

    assert {
        (
            next(
                item.offer.retailer_product_id
                for item in relationship_offers
                if item.offer.offer_id == match.benchmark_offer_id
            ),
            next(
                item.offer.retailer_product_id
                for item in relationship_offers
                if item.offer.offer_id == match.competitor_offer_id
            ),
        )
        for match in candidates
    } == {("w-1", "a-1"), ("w-2", "a-1")}
    assert resolution.relationships == ()
    assert len(resolution.ambiguous_groups) == 1


def test_confirmed_relationship_is_preserved_when_products_are_not_market_floor() -> None:
    normalizer, classifier, engine = _pipeline()
    offers = classifier.classify_many(
        normalizer.normalize_many(
            [
                _row("walmart_us", "w-1", "Fresh Organic Strawberries, 1 lb", "2.00"),
                _row("walmart_us", "w-2", "Fresh Organic Strawberries, 1 lb", "4.00"),
                _row("aldi_us", "a-1", "Fresh Organic Strawberries, 1 lb", "2.50"),
                _row("aldi_us", "a-2", "Fresh Organic Strawberries, 1 lb", "4.50"),
            ]
        )
    )
    relationship_reducer = RelationshipInputReducer(engine.pack, profile_ids={"strict"})
    relationship_reducer.extend(offers)
    relationship_offers = relationship_reducer.offers()
    governed = engine.compare_governed(
        relationship_offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
        rules=(
            ProductMatchRule(
                competitor_id="aldi_us",
                profile_id="strict",
                benchmark_product_id="w-2",
                competitor_product_id="a-2",
                decision="confirmed",
            ),
        ),
        product_candidates=True,
    )
    resolution = resolve_one_to_one_relationships(
        relationship_offers,
        governed,
        benchmark_retailer="walmart_us",
        profile_priority=("strict",),
    )

    assert {
        (
            str(row["benchmark_product_id"]),
            str(row["competitor_product_id"]),
            str(row["status"]),
        )
        for row in resolution.relationships
    } == {("w-1", "a-1", "suggested"), ("w-2", "a-2", "confirmed")}
    assert all(
        str(row["comparison_family_key"]).startswith("profile:") for row in resolution.relationships
    )


def test_governed_gold_set_mode_never_adds_automatic_relationships() -> None:
    normalizer, classifier, engine = _pipeline()
    offers = classifier.classify_many(
        normalizer.normalize_many(
            [
                _row("walmart_us", "w-1", "Fresh Organic Strawberries, 1 lb", "2.00"),
                _row("walmart_us", "w-2", "Fresh Organic Strawberries, 1 lb", "4.00"),
                _row("aldi_us", "a-1", "Fresh Organic Strawberries, 1 lb", "2.50"),
                _row("aldi_us", "a-2", "Fresh Organic Strawberries, 1 lb", "4.50"),
            ]
        )
    )
    governed = engine.compare_governed(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
        rules=(
            ProductMatchRule(
                competitor_id="aldi_us",
                profile_id="strict",
                benchmark_product_id="w-2",
                competitor_product_id="a-2",
                decision="confirmed",
            ),
        ),
        product_candidates=True,
        allow_automatic=False,
    )

    offer_index = {item.offer.offer_id: item.offer.retailer_product_id for item in offers}
    assert {
        (offer_index[match.benchmark_offer_id], offer_index[match.competitor_offer_id])
        for match in governed
    } == {("w-2", "a-2")}


def test_conflicting_product_identity_attributes_require_manual_review() -> None:
    normalizer, classifier, engine = _pipeline()
    offers = classifier.classify_many(
        normalizer.normalize_many(
            [
                _row(
                    "walmart_us",
                    "w-1",
                    "Fresh Organic Strawberries, 1 lb",
                    "3.00",
                    zipcode="10001",
                    store="w-1",
                ),
                _row(
                    "walmart_us",
                    "w-1",
                    "Fresh Strawberries, 1 lb",
                    "3.00",
                    zipcode="20002",
                    store="w-2",
                ),
                _row(
                    "aldi_us",
                    "a-1",
                    "Fresh Organic Strawberries, 1 lb",
                    "2.50",
                    zipcode="10001",
                    store="a-1",
                ),
                _row(
                    "aldi_us",
                    "a-1",
                    "Fresh Strawberries, 1 lb",
                    "2.50",
                    zipcode="20002",
                    store="a-2",
                ),
            ]
        )
    )
    candidates = engine.compare_products(
        offers,
        benchmark_id="walmart_us",
        competitor_id="aldi_us",
        profile_id="strict",
    )

    resolution = resolve_one_to_one_relationships(
        offers,
        candidates,
        benchmark_retailer="walmart_us",
        profile_priority=("strict",),
    )

    assert resolution.matches == ()
    assert resolution.relationships == ()
    assert len(resolution.ambiguous_groups) == 1
    assert resolution.ambiguous_groups[0]["reason"] == "inconsistent_product_attributes"


def test_retailer_specific_match_availability_does_not_change_scope_counts() -> None:
    offers, original = _classified()
    amazon = next(
        item
        for item in offers
        if item.offer.retailer_id == "amazon_us_same_day"
        and item.attributes["weight_oz"] == 16.0
        and item.attributes["organic"] is False
    )
    unavailable = replace(amazon, offer=replace(amazon.offer, in_stock=False))
    scoped_offers = [item for item in offers if item is not amazon]
    scoped_offers.append(unavailable)

    document = dict(original.pack.document)
    document["matching_profiles"] = [
        {
            **profile,
            "availability_policy": "retailer_specific",
        }
        for profile in original.pack.document["matching_profiles"]
    ]
    document["retailer_overrides"] = {
        "amazon_us_same_day": {"matching_availability_policy": "in_stock_only"}
    }
    engine = ComparisonEngine(replace(original.pack, document=document))

    assert unavailable.in_scope
    matches = engine.compare(
        scoped_offers,
        benchmark_id="walmart_us",
        competitor_id="amazon_us_same_day",
        profile_id="strict",
    )
    assert all(match.competitor_offer_id != unavailable.offer.offer_id for match in matches)
