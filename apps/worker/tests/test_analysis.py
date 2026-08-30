from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rci_analytics import (
    ComparisonEngine,
    InMemoryDatasetStore,
    ParquetDatasetWriter,
    ProductMatchRule,
    ProductPackLoader,
)
from rci_analytics.models import ClassifiedOffer, NormalizedOffer
from rci_collections.models import QueueTask, RawArtifact
from rci_providers import MetricsCartAdapterRegistry
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    ArtifactRenderer,
    InMemoryReportObjectStore,
    InMemoryResultsRepository,
)
from rci_worker.analysis import (
    AnalysisJob,
    AnalysisProcessor,
    CollectedPage,
    HistoricalSource,
    S3HistoricalCSVReader,
    _scoreable_competitors,
    apply_brand_classification_rules,
    historical_source_row,
    matching_v2_gold_set_presentation,
    matching_v2_gold_set_rules,
    matching_v2_reporting_coverage,
    require_matching_v2_relationship_reconciliation,
    scope_matching_v2_rules_to_brand_profiles,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "00000000-0000-0000-0000-000000000701"


def test_composite_unavailable_retailer_is_not_scored_or_silently_zeroed() -> None:
    config = {
        "benchmark_retailer": "walmart_us",
        "retailers": [
            {"retailer_id": "walmart_us", "enabled": True},
            {"retailer_id": "aldi_us", "enabled": True},
            {"retailer_id": "meijer_us", "enabled": True},
        ],
    }

    benchmark, competitors, unavailable = _scoreable_competitors(
        config, {"unavailable_retailers": ["meijer_us"]}
    )

    assert benchmark == "walmart_us"
    assert competitors == ["aldi_us"]
    assert unavailable == {"meijer_us"}


def test_composite_cannot_waive_benchmark_or_unconfigured_retailer() -> None:
    config = {
        "benchmark_retailer": "walmart_us",
        "retailers": [
            {"retailer_id": "walmart_us", "enabled": True},
            {"retailer_id": "aldi_us", "enabled": True},
        ],
    }

    with pytest.raises(ValueError, match="benchmark retailer"):
        _scoreable_competitors(config, {"unavailable_retailers": ["walmart_us"]})
    with pytest.raises(ValueError, match="unconfigured retailers"):
        _scoreable_competitors(config, {"unavailable_retailers": ["meijer_us"]})


def test_matching_v2_gold_set_rules_are_scope_aware_and_certified_only() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_shell_eggs")
    release = {
        "document": {
            "labels": [
                {
                    "case_id": "case-1",
                    "benchmark_listing_id": "walmart_us:123",
                    "competitor_listing_id": "aldi_us:abc:456",
                    "expected_comparable": True,
                    "allowed_tiers": ["equivalent_product"],
                },
                {
                    "case_id": "case-2",
                    "benchmark_listing_id": "walmart_us:789",
                    "competitor_listing_id": "target_us:987",
                    "expected_comparable": False,
                    "allowed_tiers": [],
                },
            ]
        }
    }

    rules = matching_v2_gold_set_rules(release, pack)

    assert [rule.decision for rule in rules] == ["confirmed", "rejected"]
    assert rules[0].competitor_product_id == "abc:456"
    assert rules[0].scope_mode == "observed_benchmark_product_footprint"
    assert rules[0].eligible_profile_ids


@pytest.mark.parametrize(
    ("product_pack_id", "allowed_tier", "expected_profiles"),
    [
        (
            "fresh_strawberries",
            "exact_specification",
            ("strict", "unit_price", "aldi_10mi"),
        ),
        ("fresh_ground_beef", "equivalent_product", ("unit_price",)),
        ("vitamins_supplements", "equivalent_product", ("compatible_spec",)),
    ],
)
def test_matching_v2_certified_rules_use_location_comparable_profiles(
    product_pack_id: str,
    allowed_tier: str,
    expected_profiles: tuple[str, ...],
) -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load(product_pack_id)
    release = {
        "document": {
            "labels": [
                {
                    "case_id": "case-current",
                    "benchmark_listing_id": "walmart_us:w-1",
                    "competitor_listing_id": "aldi_us:a-1",
                    "expected_comparable": True,
                    "allowed_tiers": [allowed_tier],
                }
            ]
        }
    }

    rules = matching_v2_gold_set_rules(release, pack)

    assert rules[0].eligible_profile_ids == expected_profiles


def test_matching_v2_certified_rules_preserve_explicit_price_basis() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    release = {
        "document": {
            "labels": [
                {
                    "case_id": "case-unit-only",
                    "benchmark_listing_id": "walmart_us:787374421",
                    "competitor_listing_id": "target_us:50282227",
                    "expected_comparable": True,
                    "allowed_tiers": ["exact_specification"],
                    "eligible_price_bases": ["normalized_unit"],
                }
            ]
        }
    }

    rules = matching_v2_gold_set_rules(release, pack)

    assert rules[0].eligible_profile_ids == ("compatible_spec",)
    assert rules[0].scope_definition == {
        "certified_allowed_tiers": ["exact_specification"],
        "certified_price_bases": ["normalized_unit"],
        "certified_price_basis_authority": True,
    }


def test_matching_v2_certified_relationship_without_price_basis_is_retained_without_math() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    release = {
        "document": {
            "labels": [
                {
                    "case_id": "case-no-price-basis",
                    "benchmark_listing_id": "walmart_us:w-1",
                    "competitor_listing_id": "walgreens_us:x-1",
                    "expected_comparable": True,
                    "allowed_tiers": ["equivalent_product"],
                    "eligible_price_bases": [],
                }
            ]
        }
    }

    rules = matching_v2_gold_set_rules(release, pack)
    scoped = scope_matching_v2_rules_to_brand_profiles(
        [],
        rules,
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
        engine=ComparisonEngine(pack),
    )
    relationships, candidates = matching_v2_gold_set_presentation(
        [],
        scoped,
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
    )

    assert scoped[0].eligible_profile_ids == ("certified_no_price_basis",)
    assert len(relationships) == 1
    assert relationships[0]["eligible_profile_ids"] == []
    assert candidates == []


def test_matching_v2_package_price_rejects_explicit_multipack_mismatch() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_ground_beef")
    engine = ComparisonEngine(pack)

    def offer(retailer_id: str, product_id: str, title: str) -> ClassifiedOffer:
        return ClassifiedOffer(
            offer=NormalizedOffer(
                offer_id=f"{retailer_id}:{product_id}:offer",
                retailer_id=retailer_id,
                retailer_product_id=product_id,
                title=title,
                brand=None,
                price=Decimal("6.00"),
                currency="USD",
                zipcode="72712",
                store_number="100",
                latitude=None,
                longitude=None,
                in_stock=True,
                product_url=None,
                image_url=None,
                collected_at="2026-08-20T12:00:00+00:00",
                raw={},
            ),
            in_scope=True,
            scope_reason=None,
            attributes={
                "lean_pct": 85,
                "fat_pct": 15,
                "weight_lb": 1.0,
                "organic": True,
                "grass_fed": True,
                "premium_tier": "standard",
            },
            metrics={"price_per_lb": Decimal("6.00")},
            review_reasons=(),
        )

    rules = [
        ProductMatchRule(
            competitor_id="aldi_us",
            profile_id="strict",
            benchmark_product_id="w-multi",
            competitor_product_id="a-single",
            decision="confirmed",
            eligible_profile_ids=("strict", "unit_price"),
            scope_definition={"certified_allowed_tiers": ["exact_specification"]},
        )
    ]
    scoped = scope_matching_v2_rules_to_brand_profiles(
        [
            offer("walmart_us", "w-multi", "Organic Ground Beef, 1 lb, 3 Count"),
            offer("aldi_us", "a-single", "Organic Ground Beef, 1 lb"),
        ],
        rules,
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
        engine=engine,
    )

    assert scoped[0].eligible_profile_ids == ("unit_price",)


def test_matching_v2_certified_price_basis_is_not_rejected_by_search_reclassification() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    engine = ComparisonEngine(pack)

    def offer(retailer_id: str, product_id: str, package_count: int) -> ClassifiedOffer:
        return ClassifiedOffer(
            offer=NormalizedOffer(
                offer_id=f"{retailer_id}:{product_id}:offer",
                retailer_id=retailer_id,
                retailer_product_id=product_id,
                title="Vitamin B12 Quick Dissolve",
                brand="Spring Valley" if retailer_id == "walmart_us" else "up&up",
                price=Decimal("9.00"),
                currency="USD",
                zipcode="72712",
                store_number="100",
                latitude=36.37,
                longitude=-94.21,
                in_stock=True,
                product_url=None,
                image_url=None,
                collected_at="2026-08-20T12:00:00+00:00",
                raw={},
            ),
            in_scope=True,
            scope_reason=None,
            attributes={
                "active_ingredient": "vitamin_b12",
                "strength": 5000,
                "strength_unit": "mcg",
                "dosage_form": "quick_dissolve_tablet",
                "package_count": package_count,
                "release_profile": "immediate_release",
                "life_stage": "adult",
                "brand": "Spring Valley" if retailer_id == "walmart_us" else "up&up",
            },
            metrics={"price_per_item": Decimal("0.03")},
            review_reasons=(),
        )

    rule = ProductMatchRule(
        competitor_id="target_us",
        profile_id="compatible_spec",
        benchmark_product_id="787374421",
        competitor_product_id="50282227",
        decision="confirmed",
        eligible_profile_ids=("compatible_spec",),
        scope_definition={
            "certified_allowed_tiers": ["equivalent_product"],
            "certified_price_bases": ["normalized_unit"],
        },
    )
    scoped = scope_matching_v2_rules_to_brand_profiles(
        [
            offer("walmart_us", "787374421", 300),
            offer("target_us", "50282227", 120),
        ],
        [rule],
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
        engine=engine,
    )

    assert scoped[0].eligible_profile_ids == ("compatible_spec",)


def test_matching_v2_certified_price_basis_retains_unobserved_brand_neutral_pair() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("vitamins_supplements")
    engine = ComparisonEngine(pack)
    rule = ProductMatchRule(
        competitor_id="target_us",
        profile_id="compatible_spec",
        benchmark_product_id="787374421",
        competitor_product_id="50282227",
        decision="confirmed",
        eligible_profile_ids=("compatible_spec",),
        scope_definition={
            "certified_allowed_tiers": ["equivalent_product"],
            "certified_price_bases": ["normalized_unit"],
        },
    )

    scoped = scope_matching_v2_rules_to_brand_profiles(
        [],
        [rule],
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
        engine=engine,
    )

    assert scoped[0].eligible_profile_ids == ("compatible_spec",)


def test_matching_v2_certified_banana_pair_honors_role_specific_profile_constraints() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_bananas")
    engine = ComparisonEngine(pack)

    def offer(retailer_id: str, product_id: str) -> ClassifiedOffer:
        return ClassifiedOffer(
            offer=NormalizedOffer(
                offer_id=f"{retailer_id}:{product_id}:offer",
                retailer_id=retailer_id,
                retailer_product_id=product_id,
                title="Organic Bananas Bunch, 2.25 lb",
                brand=None,
                price=Decimal("3.00"),
                currency="USD",
                zipcode="72712",
                store_number="100",
                latitude=None,
                longitude=None,
                in_stock=True,
                product_url=None,
                image_url=None,
                collected_at="2026-08-20T12:00:00+00:00",
                raw={},
            ),
            in_scope=True,
            scope_reason=None,
            attributes={
                "variety": "Standard Yellow",
                "organic": True,
                "selling_unit": "bunch",
                "weight_lb": 2.25,
                "count_min": None,
                "count_max": None,
                "retailer_product_id": product_id,
            },
            metrics={"price_per_lb": Decimal("1.3333")},
            review_reasons=(),
        )

    rule = ProductMatchRule(
        competitor_id="amazon_us_same_day",
        profile_id="weight_normalized",
        benchmark_product_id="51259338",
        competitor_product_id="B0FNNCZ18K",
        decision="confirmed",
        eligible_profile_ids=(
            "weight_normalized",
            "count_compatible",
            "conventional_bunch_range",
            "organic_bunch_midpoint",
        ),
        scope_definition={"certified_allowed_tiers": ["equivalent_product"]},
    )
    scoped = scope_matching_v2_rules_to_brand_profiles(
        [
            offer("walmart_us", "51259338"),
            offer("amazon_us_same_day", "B0FNNCZ18K"),
        ],
        [rule],
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
        engine=engine,
    )

    assert scoped[0].eligible_profile_ids == ("weight_normalized", "count_compatible")


def test_matching_v2_unobserved_certified_pair_keeps_only_generic_profiles() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_bananas")
    engine = ComparisonEngine(pack)
    rule = ProductMatchRule(
        competitor_id="amazon_us_same_day",
        profile_id="weight_normalized",
        benchmark_product_id="51259338",
        competitor_product_id="B0FNNCZ18K",
        decision="confirmed",
        eligible_profile_ids=(
            "weight_normalized",
            "count_compatible",
            "conventional_bunch_range",
            "organic_bunch_midpoint",
        ),
        scope_definition={"certified_allowed_tiers": ["equivalent_product"]},
    )

    scoped = scope_matching_v2_rules_to_brand_profiles(
        [],
        [rule],
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
        engine=engine,
    )

    assert scoped[0].eligible_profile_ids == ("weight_normalized", "count_compatible")


def test_matching_v2_certified_rules_are_segmented_by_governed_brand_policy() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    engine = ComparisonEngine(pack)
    profile_ids = tuple(str(profile["id"]) for profile in pack.matching_profiles)

    def offer(
        retailer_id: str,
        product_id: str,
        brand: str | None,
    ) -> ClassifiedOffer:
        return ClassifiedOffer(
            offer=NormalizedOffer(
                offer_id=f"{retailer_id}:{product_id}:offer",
                retailer_id=retailer_id,
                retailer_product_id=product_id,
                title=f"{brand or 'Unknown'} milk",
                brand=brand,
                price=Decimal("3.00"),
                currency="USD",
                zipcode="72712",
                store_number="100",
                latitude=None,
                longitude=None,
                in_stock=True,
                product_url=None,
                image_url=None,
                collected_at="2026-08-20T12:00:00+00:00",
                raw={},
            ),
            in_scope=True,
            scope_reason=None,
            attributes={"brand": brand} if brand is not None else {},
            metrics={"price_per_gallon": Decimal("3.00")},
            review_reasons=(),
        )

    rules = [
        ProductMatchRule(
            competitor_id="aldi_us",
            profile_id=profile_ids[0],
            benchmark_product_id=benchmark_product_id,
            competitor_product_id=competitor_product_id,
            decision=decision,
            eligible_profile_ids=profile_ids,
        )
        for benchmark_product_id, competitor_product_id, decision in (
            ("w-private", "a-private", "confirmed"),
            ("w-same", "a-same", "confirmed"),
            ("w-cross", "a-cross", "confirmed"),
            ("w-unknown", "a-unknown", "confirmed"),
            ("w-rejected", "a-rejected", "rejected"),
        )
    ]
    offers = [
        offer("walmart_us", "w-private", "Great Value"),
        offer("aldi_us", "a-private", "Friendly Farms"),
        offer("walmart_us", "w-same", "Horizon Organic"),
        offer("aldi_us", "a-same", "Horizon Organic"),
        offer("walmart_us", "w-cross", "Hiland"),
        offer("aldi_us", "a-cross", "Friendly Farms"),
        offer("walmart_us", "w-unknown", None),
        offer("aldi_us", "a-unknown", None),
    ]

    scoped = scope_matching_v2_rules_to_brand_profiles(
        offers,
        rules,
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
        engine=engine,
    )

    assert scoped[0].eligible_profile_ids == ("private_label", "all_brand")
    assert scoped[1].eligible_profile_ids == ("same_brand_exact", "all_brand")
    assert scoped[2].eligible_profile_ids == ("all_brand",)
    assert scoped[3].eligible_profile_ids == ("all_brand",)
    assert scoped[4].eligible_profile_ids == profile_ids


def test_matching_v2_profile_gate_uses_current_search_correction_for_static_override() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    engine = ComparisonEngine(pack)
    dimensions = {
        "volume_oz": 128,
        "fat_type": "2%",
        "flavor": "Plain",
        "organic": False,
        "lactose_free": False,
        "ultrafiltered": False,
        "a2": False,
        "grass_fed": False,
        "omega_3_dha": False,
        "kids": False,
        "protein_fortified": False,
    }

    def offer(
        retailer_id: str,
        product_id: str,
        title: str,
        brand: str,
        fat_type: str,
    ) -> ClassifiedOffer:
        attributes = {**dimensions, "brand": brand, "fat_type": fat_type}
        return ClassifiedOffer(
            offer=NormalizedOffer(
                offer_id=f"{retailer_id}:{product_id}:offer",
                retailer_id=retailer_id,
                retailer_product_id=product_id,
                title=title,
                brand=brand,
                price=Decimal("3.00"),
                currency="USD",
                zipcode="72712",
                store_number="100",
                latitude=None,
                longitude=None,
                in_stock=True,
                product_url=None,
                image_url=None,
                collected_at="2026-08-20T12:00:00+00:00",
                raw={},
            ),
            in_scope=True,
            scope_reason=None,
            attributes={
                **attributes,
                "_attribute_provenance": {name: "product_pack_override" for name in attributes},
            },
            metrics={"price_per_gallon": Decimal("3.00")},
            review_reasons=(),
        )

    rule = ProductMatchRule(
        competitor_id="amazon_us_same_day",
        profile_id="same_brand_exact",
        benchmark_product_id="10450115",
        competitor_product_id="B07NSWQHB1",
        decision="confirmed",
        eligible_profile_ids=("same_brand_exact", "private_label", "all_brand"),
        scope_definition={"certified_allowed_tiers": ["exact_specification"]},
    )
    scoped = scope_matching_v2_rules_to_brand_profiles(
        [
            offer(
                "walmart_us",
                "10450115",
                "Great Value, 2% Reduced Fat Milk, Gallon",
                "Great Value",
                "2%",
            ),
            offer(
                "amazon_us_same_day",
                "B07NSWQHB1",
                "365 by Whole Foods Market Reduced Fat Milk, 128 OZ",
                "365 by Whole Foods Market",
                "Whole",
            ),
        ],
        [rule],
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
        engine=engine,
    )

    assert scoped[0].eligible_profile_ids == ("private_label", "all_brand")


def test_gold_set_presentation_retains_certified_pair_without_exact_zip_overlap() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_shell_eggs")
    release = {
        "document": {
            "labels": [
                {
                    "case_id": "case-sams",
                    "benchmark_listing_id": "walmart_us:w-1",
                    "competitor_listing_id": "sams_club_us:s-1",
                    "expected_comparable": True,
                    "allowed_tiers": ["equivalent_product"],
                }
            ]
        }
    }
    rules = matching_v2_gold_set_rules(release, pack)

    def offer(
        offer_id: str,
        retailer_id: str,
        product_id: str,
        zipcode: str,
    ) -> ClassifiedOffer:
        return ClassifiedOffer(
            offer=NormalizedOffer(
                offer_id=offer_id,
                retailer_id=retailer_id,
                retailer_product_id=product_id,
                title=f"{retailer_id} large eggs",
                brand=None,
                price=Decimal("3.00"),
                currency="USD",
                zipcode=zipcode,
                store_number="100",
                latitude=None,
                longitude=None,
                in_stock=True,
                product_url=None,
                image_url=None,
                collected_at="2026-08-20T12:00:00+00:00",
                raw={},
            ),
            in_scope=True,
            scope_reason=None,
            attributes={
                "count": 12.0,
                "size": "Large",
                "shell_color": "White",
            },
            metrics={"price_per_dozen": Decimal("3.00")},
            review_reasons=(),
        )

    relationships, candidates = matching_v2_gold_set_presentation(
        [
            offer("w-offer", "walmart_us", "w-1", "72712"),
            offer("s-offer", "sams_club_us", "s-1", "10001"),
        ],
        rules,
        benchmark_retailer="walmart_us",
        profiles=pack.matching_profiles,
    )

    assert len(relationships) == 1
    assert relationships[0]["status"] == "confirmed"
    assert relationships[0]["benchmark_location_scope_keys"] == ["walmart_us|72712|100"]
    assert candidates
    assert {row["competitor"] for row in candidates} == {"sams_club_us"}
    assert all(row["relationship_status"] == "confirmed" for row in candidates)
    assert all(row["matches"] == 0 for row in candidates)
    require_matching_v2_relationship_reconciliation(
        relationships,
        {
            "certified_comparable_count": 1,
            "retailers": [
                {
                    "competitor_retailer_id": "sams_club_us",
                    "certified_comparable_count": 1,
                }
            ],
        },
    )


def test_gold_set_presentation_reconciliation_fails_when_relationship_is_lost() -> None:
    with pytest.raises(ValueError, match="does not reconcile"):
        require_matching_v2_relationship_reconciliation(
            [],
            {
                "certified_comparable_count": 1,
                "retailers": [
                    {
                        "competitor_retailer_id": "shoprite_us",
                        "certified_comparable_count": 1,
                    }
                ],
            },
        )


def test_matching_v2_reconciliation_projects_out_unavailable_retailer_labels() -> None:
    coverage = {
        "authority": "matching_v2_certified_gold_set",
        "selection_complete": True,
        "automatic_fallback_enabled": False,
        "retailers": [
            {
                "competitor_retailer_id": "aldi_us",
                "candidate_count": 2,
                "certified_count": 2,
                "certified_comparable_count": 1,
                "certified_not_comparable_count": 1,
                "unresolved_count": 0,
            },
            {
                "competitor_retailer_id": "wegmans_us",
                "candidate_count": 3,
                "certified_count": 3,
                "certified_comparable_count": 2,
                "certified_not_comparable_count": 1,
                "unresolved_count": 0,
            },
        ],
        "certified_comparable_count": 3,
    }
    relationships = [
        {
            "relationship_id": "relationship-aldi",
            "competitor_id": "aldi_us",
            "status": "confirmed",
        }
    ]

    reporting = matching_v2_reporting_coverage(coverage, {"wegmans_us"})
    require_matching_v2_relationship_reconciliation(
        relationships,
        coverage,
        unavailable_retailers={"wegmans_us"},
    )

    assert reporting["certified_comparable_count"] == 1
    assert reporting["withheld_certified_comparable_count"] == 2
    assert reporting["scoreable_retailer_ids"] == ["aldi_us"]
    assert reporting["unavailable_retailer_ids"] == ["wegmans_us"]
    assert reporting["retailers"][0]["competitor_retailer_id"] == "aldi_us"
    assert reporting["excluded_unavailable_retailers"][0]["competitor_retailer_id"] == "wegmans_us"

    with pytest.raises(ValueError, match="emitted unavailable retailers"):
        require_matching_v2_relationship_reconciliation(
            [
                *relationships,
                {
                    "relationship_id": "relationship-wegmans",
                    "competitor_id": "wegmans_us",
                    "status": "confirmed",
                },
            ],
            coverage,
            unavailable_retailers={"wegmans_us"},
        )
    with pytest.raises(ValueError, match="does not reconcile"):
        require_matching_v2_relationship_reconciliation(
            [],
            coverage,
            unavailable_retailers={"wegmans_us"},
        )


def _task(
    retailer_id: str,
    adapter_id: str,
    product_id: str,
    store_number: str | None,
) -> QueueTask:
    now = datetime.now(UTC)
    return QueueTask(
        id=f"00000000-0000-0000-0000-{product_id[-12:].zfill(12)}",
        collection_run_id=RUN_ID,
        retailer_id=retailer_id,
        retailer_location_id=None,
        adapter_id=adapter_id,
        location_scope_key="zip:44906",
        zipcode="44906",
        store_number=store_number,
        page_number=1,
        max_pages=1,
        stop_on_empty=True,
        stop_on_short_page=False,
        credits_per_success=1 if retailer_id == "walmart_us" else 2,
        request_payload={"keyword": "strawberries"},
        request_fingerprint=f"fingerprint-{retailer_id}",
        status="succeeded",
        priority=100,
        attempt_count=1,
        max_attempts=5,
        available_at=now,
        locked_by=None,
        lease_expires_at=now + timedelta(minutes=5),
        created_at=now,
        http_status=200,
        result_count=1,
        billable_credits=1 if retailer_id == "walmart_us" else 2,
        raw_artifact_id=f"raw-{retailer_id}",
    )


class PageQueue:
    def __init__(self, pages: list[CollectedPage]) -> None:
        self._pages = pages

    async def pages(self, run_id: str) -> list[CollectedPage]:
        assert run_id == RUN_ID
        return self._pages

    async def composite_pages(self, input_set_id: str) -> list[CollectedPage]:
        assert input_set_id == "00000000-0000-0000-0000-000000000713"
        return self._pages


class HistoricalQueue:
    def __init__(self, sources: list[HistoricalSource]) -> None:
        self._sources = sources

    async def historical_sources(self, input_set_id: str) -> list[HistoricalSource]:
        assert input_set_id == "00000000-0000-0000-0000-000000000704"
        return self._sources


class RawReader:
    def __init__(self, payloads: dict[str, object]) -> None:
        self._payloads = payloads

    async def read(self, page: CollectedPage) -> object:
        return self._payloads[page.task.id]


class HistoricalReader:
    def __init__(self, rows: dict[str, list[dict[str, str]]]) -> None:
        self._rows = rows

    async def read(self, source: HistoricalSource) -> list[dict[str, str]]:
        return self._rows[source.retailer_id]


class ArtifactRecorder:
    def __init__(self) -> None:
        self.artifacts: list[RawArtifact] = []

    async def record_artifact(self, run_id: str, artifact: RawArtifact) -> str:
        assert run_id == RUN_ID
        self.artifacts.append(artifact)
        return artifact.storage_uri


def _payload(product_id: str, price: str) -> dict[str, Any]:
    return {
        "results": [
            {
                "name": "Fresh Strawberries, 1 lb",
                "brand": "Fresh Produce",
                "price": price,
                "retailer_product_id": product_id,
                "url": f"https://retailer.example/items/{product_id}",
                "stock_availability": True,
            }
        ]
    }


def test_consolidated_historical_rows_keep_their_own_retailer_identity() -> None:
    source = HistoricalSource(
        dataset_artifact_id="artifact-eggs",
        input_set_id="input-eggs",
        ordinal=0,
        retailer_id="walmart_us",
        adapter_id="historical_metricscart_consolidated_serp_csv",
        source_name="eggs.csv",
        source_format="metricscart_consolidated_serp_csv",
        storage_uri="s3://raw/eggs.csv",
        checksum="a" * 64,
        row_count=1,
    )

    assert historical_source_row({"Retailer": "aldi.us"}, source) == {"Retailer": "aldi.us"}


def test_single_retailer_historical_rows_use_the_manifest_retailer() -> None:
    source = HistoricalSource(
        dataset_artifact_id="artifact-walmart",
        input_set_id="input-walmart",
        ordinal=0,
        retailer_id="walmart_us",
        adapter_id="historical_metricscart_search_monitor_csv",
        source_name="walmart.csv",
        source_format="metricscart_search_monitor_csv",
        storage_uri="s3://raw/walmart.csv",
        checksum="a" * 64,
        row_count=1,
    )

    assert historical_source_row({"Retailer": "incorrect"}, source)["retailer_id"] == ("walmart_us")


async def test_completed_collection_runs_through_generic_product_pack_pipeline() -> None:
    specifications = [
        (
            "walmart_us",
            "metricscart_walmart_search_zipcode_v2",
            "44391605",
            "2040",
            "$2.98",
        ),
        (
            "aldi_us",
            "metricscart_new_aldi_serp_zipcode",
            "16383764",
            "463-048",
            "$2.49",
        ),
        (
            "amazon_us_same_day",
            "metricscart_amazon_same_day_zipcode",
            "B000P6J0SM",
            None,
            "$3.49",
        ),
    ]
    now = datetime.now(UTC)
    pages: list[CollectedPage] = []
    payloads: dict[str, object] = {}
    for retailer_id, adapter_id, product_id, store_number, price in specifications:
        task = _task(retailer_id, adapter_id, product_id, store_number)
        pages.append(
            CollectedPage(
                task=task,
                storage_uri=f"s3://raw/{task.id}.json.gz",
                checksum="a" * 64,
                collected_at=now,
                latitude=40.7584,
                longitude=-82.5154,
            )
        )
        payloads[task.id] = _payload(product_id, price)

    result_repository = InMemoryResultsRepository()
    result_service = AnalysisResultService(
        result_repository,
        AnalysisResultValidator(REPOSITORY_ROOT),
        InMemoryReportObjectStore(),
    )
    dataset_store = InMemoryDatasetStore()
    artifact_recorder = ArtifactRecorder()
    processor = AnalysisProcessor(
        repository_root=REPOSITORY_ROOT,
        queue=PageQueue(pages),  # type: ignore[arg-type]
        adapters=MetricsCartAdapterRegistry.from_catalog(
            REPOSITORY_ROOT / "config" / "retailer-catalog.json"
        ),
        raw_reader=RawReader(payloads),  # type: ignore[arg-type]
        dataset_writer=ParquetDatasetWriter(dataset_store),
        collections=artifact_recorder,  # type: ignore[arg-type]
        results=result_service,
        code_version="test-version",
    )
    job = AnalysisJob(
        id="00000000-0000-0000-0000-000000000702",
        collection_run_id=RUN_ID,
        input_set_id="00000000-0000-0000-0000-000000000703",
        source_kind="live_collection",
        product_pack_id="fresh_strawberries",
        product_pack_version="1.1.0",
        definition_config={
            "benchmark_retailer": "walmart_us",
            "retailers": [
                {"retailer_id": retailer_id, "enabled": True} for retailer_id, *_ in specifications
            ],
            "delivery": {
                "web_report": False,
                "excel": False,
                "leadership_email": False,
                "audit_package": False,
            },
        },
        attempt_count=1,
        max_attempts=3,
    )

    analysis_id = await processor.process(job)

    analysis = await result_service.get_by_collection_run(RUN_ID)
    assert analysis.analysis_id == analysis_id
    assert analysis.result["schema_version"] == "2.0.0"
    assert analysis.result["source"]["total_rows"] == 3
    assert {row["retailer_id"] for row in analysis.result["coverage"]} == {
        "walmart_us",
        "aldi_us",
        "amazon_us_same_day",
    }
    assert analysis.result["comparisons"]
    assert {mode["comparison_metric"] for mode in analysis.result["comparison_modes"]} == {
        "package_price",
        "price_per_lb",
    }
    assert len(artifact_recorder.artifacts) >= 7
    assert all(uri.endswith(".parquet") for uri in dataset_store.objects)
    publication = await result_service.latest_publication(analysis_id)
    assert publication is not None
    map_points = publication.presentation_context["map_points"]
    assert isinstance(map_points, list)
    assert map_points == []
    suppressed = publication.presentation_context["suppressed_product_decisions"]
    assert suppressed
    assert all(row["qa_status"] == "suppressed" for row in suppressed)
    assert all(
        "Requires at least 25 retained observations" in row["suppression_reasons"]
        for row in suppressed
    )


async def test_composite_unavailable_competitor_is_declared_but_never_scored() -> None:
    specifications = [
        ("walmart_us", "metricscart_walmart_search_zipcode_v2", "44391605", "2040", "$2.98"),
        ("aldi_us", "metricscart_new_aldi_serp_zipcode", "16383764", "463-048", "$2.49"),
    ]
    now = datetime.now(UTC)
    pages: list[CollectedPage] = []
    payloads: dict[str, object] = {}
    for retailer_id, adapter_id, product_id, store_number, price in specifications:
        task = _task(retailer_id, adapter_id, product_id, store_number)
        pages.append(
            CollectedPage(
                task=task,
                storage_uri=f"s3://raw/{task.id}.json.gz",
                checksum="b" * 64,
                collected_at=now,
                latitude=40.7584,
                longitude=-82.5154,
            )
        )
        payloads[task.id] = _payload(product_id, price)

    result_service = AnalysisResultService(
        InMemoryResultsRepository(),
        AnalysisResultValidator(REPOSITORY_ROOT),
        InMemoryReportObjectStore(),
    )
    processor = AnalysisProcessor(
        repository_root=REPOSITORY_ROOT,
        queue=PageQueue(pages),  # type: ignore[arg-type]
        adapters=MetricsCartAdapterRegistry.from_catalog(
            REPOSITORY_ROOT / "config" / "retailer-catalog.json"
        ),
        raw_reader=RawReader(payloads),  # type: ignore[arg-type]
        dataset_writer=ParquetDatasetWriter(InMemoryDatasetStore()),
        collections=ArtifactRecorder(),  # type: ignore[arg-type]
        results=result_service,
        code_version="test-version",
    )
    job = AnalysisJob(
        id="00000000-0000-0000-0000-000000000712",
        collection_run_id=RUN_ID,
        input_set_id="00000000-0000-0000-0000-000000000713",
        source_kind="live_collection_composite",
        product_pack_id="fresh_strawberries",
        product_pack_version="1.1.0",
        definition_config={
            "benchmark_retailer": "walmart_us",
            "retailers": [
                {"retailer_id": "walmart_us", "enabled": True},
                {"retailer_id": "aldi_us", "enabled": True},
                {"retailer_id": "amazon_us_same_day", "enabled": True},
            ],
            "delivery": {
                "web_report": False,
                "excel": False,
                "leadership_email": False,
                "audit_package": False,
            },
        },
        attempt_count=1,
        max_attempts=3,
        input_manifest_checksum="c" * 64,
        component_collection_run_ids=(RUN_ID, "recovery-run"),
        input_manifest={
            "unavailable_retailers": ["amazon_us_same_day"],
            "scope_projections": [
                {
                    "id": "00000000-0000-0000-0000-000000000714",
                    "retailer_id": "amazon_us_same_day",
                    "projection_kind": "limited_provider_footprint",
                    "policy_version": "collection-scope-projection-v1",
                    "projection_checksum": "d" * 64,
                    "source_audit_id": None,
                    "source_evidence_checksum": "e" * 64,
                    "raw_task_count": 114,
                    "retained_task_count": 89,
                    "excluded_task_count": 25,
                    "raw_location_count": 114,
                    "retained_location_count": 89,
                    "excluded_location_count": 25,
                    "raw_task_retention_ratio": "0.780702",
                    "governed_coverage_ratio": "0.780702",
                    "minimum_scoreable_coverage": "0.950000",
                    "scorecard_disposition": "unavailable",
                    "inventory_checksum": "f" * 64,
                }
            ],
            "retailer_collection_readiness": {
                "amazon_us_same_day": {
                    "status": "unavailable",
                    "unavailability_approval": {
                        "reason": "provider evidence remained insufficient"
                    },
                }
            },
        },
    )

    analysis_id = await processor.process(job)
    analysis = await result_service.get_by_collection_run(RUN_ID)
    assert analysis.result["competitors"] == ["aldi_us", "amazon_us_same_day"]
    assert analysis.result["source"]["unavailable_retailers"] == ["amazon_us_same_day"]
    assert (
        analysis.result["source"]["collection_scope_projections"][0]["governed_coverage_ratio"]
        == "0.780702"
    )
    assert all(
        row.get("competitor_id") != "amazon_us_same_day"
        for row in analysis.result.get("comparisons", [])
    )
    assortment = analysis.result.get("assortment_analysis", {})
    assert all(
        row.get("retailer_id") != "amazon_us_same_day" for row in assortment.get("retailers", [])
    )
    publication = await result_service.latest_publication(analysis_id)
    assert publication is not None
    assert analysis.result["validation"]["status"] == "ready_to_share"
    readiness = ArtifactRenderer(REPOSITORY_ROOT).report_view(analysis.result)["report_readiness"]
    assert readiness["status"] in {"ready", "limited"}
    assert not readiness["blocking_reasons"]
    assert all(
        row.get("code") != "analysis_validation_not_ready" for row in readiness["blocking_reasons"]
    )
    assert any(row.get("code") == "competitor_data_unavailable" for row in readiness["warnings"])


async def test_historical_input_replays_through_same_generic_pipeline() -> None:
    retailer_ids = ("walmart_us", "aldi_us", "amazon_us_same_day")
    input_set_id = "00000000-0000-0000-0000-000000000704"
    sources = [
        HistoricalSource(
            dataset_artifact_id=f"artifact-{retailer_id}",
            input_set_id=input_set_id,
            ordinal=index,
            retailer_id=retailer_id,
            adapter_id="historical_metricscart_search_monitor_csv",
            source_name=f"{retailer_id}.csv",
            source_format="metricscart_search_monitor_csv",
            storage_uri=f"s3://raw/{retailer_id}.csv",
            checksum=f"{index}" * 64,
            row_count=1,
        )
        for index, retailer_id in enumerate(retailer_ids, start=1)
    ]
    product_ids = {
        "walmart_us": "44391605",
        "aldi_us": "16383764",
        "amazon_us_same_day": "B000P6J0SM",
    }
    timestamps = {
        "walmart_us": "2026-08-07T05:03:04.869637",
        "aldi_us": "2026-08-07T05:04:05Z",
        "amazon_us_same_day": "1.786118963679E+12",
    }
    rows = {
        retailer_id: [
            {
                "Retailer Store Id": "0007" if retailer_id != "amazon_us_same_day" else "",
                "Zipcode": "00617",
                "Retailer Product Id": product_ids[retailer_id],
                "Product Name": "Fresh Strawberries, 1 lb",
                "Price": price,
                "Stock Availability": "true",
                "Date": timestamps[retailer_id],
            }
        ]
        for retailer_id, price in zip(retailer_ids, ("2.98", "2.49", "3.49"), strict=True)
    }
    result_repository = InMemoryResultsRepository()
    result_service = AnalysisResultService(
        result_repository,
        AnalysisResultValidator(REPOSITORY_ROOT),
        InMemoryReportObjectStore(),
    )
    dataset_store = InMemoryDatasetStore()
    artifact_recorder = ArtifactRecorder()
    processor = AnalysisProcessor(
        repository_root=REPOSITORY_ROOT,
        queue=HistoricalQueue(sources),  # type: ignore[arg-type]
        adapters=MetricsCartAdapterRegistry.from_catalog(
            REPOSITORY_ROOT / "config" / "retailer-catalog.json"
        ),
        raw_reader=RawReader({}),  # type: ignore[arg-type]
        historical_reader=HistoricalReader(rows),  # type: ignore[arg-type]
        dataset_writer=ParquetDatasetWriter(dataset_store),
        collections=artifact_recorder,  # type: ignore[arg-type]
        results=result_service,
        code_version="test-version",
    )
    job = AnalysisJob(
        id="00000000-0000-0000-0000-000000000705",
        collection_run_id=RUN_ID,
        input_set_id=input_set_id,
        source_kind="historical_import",
        product_pack_id="fresh_strawberries",
        product_pack_version="1.1.0",
        definition_config={
            "benchmark_retailer": "walmart_us",
            "retailers": [
                {"retailer_id": retailer_id, "enabled": True} for retailer_id in retailer_ids
            ],
            "analysis": {"comparison_profiles": ["strict"]},
            "delivery": {},
        },
        attempt_count=1,
        max_attempts=3,
    )

    analysis_id = await processor.process(job)

    analysis = await result_service.get_by_collection_run(RUN_ID)
    assert analysis.analysis_id == analysis_id
    assert analysis.result["source"]["kind"] == "historical_import"
    assert analysis.result["source"]["total_rows"] == 3
    assert analysis.result["source"]["observed_start"] == "2026-08-07T05:03:04.869637Z"
    assert analysis.result["source"]["observed_end"] == "2026-08-07T16:09:23.679000Z"
    assert analysis.result["source"]["source_artifact_ids"] == sorted(
        source.dataset_artifact_id for source in sources
    )
    assert analysis.result["comparisons"]


def test_analysis_orchestrator_has_no_product_category_branches() -> None:
    source = (REPOSITORY_ROOT / "apps/worker/src/rci_worker/analysis.py").read_text()
    assert "fresh_strawberries" not in source
    assert "fresh_shell_eggs" not in source
    assert "fresh_ground_beef" not in source


def test_brand_revision_adds_and_removes_private_label_without_mutating_pack() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_fluid_milk")
    rules = [
        SimpleNamespace(
            retailer_id="walmart_us",
            normalized_brand="hiland dairy",
            display_brand="Hiland Dairy",
            role="private_label",
            decision="confirmed",
        ),
        SimpleNamespace(
            retailer_id="walmart_us",
            normalized_brand="great value",
            display_brand="Great Value",
            role="private_label",
            decision="rejected",
        ),
    ]

    governed = apply_brand_classification_rules(pack, rules)  # type: ignore[arg-type]

    assert "Hiland Dairy" in governed.document["brand_rules"]["private_labels"]["walmart_us"]
    assert "Great Value" not in governed.document["brand_rules"]["private_labels"]["walmart_us"]
    assert "Hiland Dairy" not in pack.document["brand_rules"]["private_labels"]["walmart_us"]
    assert "Great Value" in pack.document["brand_rules"]["private_labels"]["walmart_us"]


async def test_historical_reader_yields_checksum_verified_bounded_batches() -> None:
    body = b"Retailer Product Id,Product Name,Price\n1,One,1.00\n2,Two,2.00\n3,Three,3.00\n"

    class Client:
        def get_object(self, **kwargs: object) -> dict[str, BytesIO]:
            assert kwargs == {"Bucket": "raw", "Key": "history.csv"}
            return {"Body": BytesIO(body)}

    source = HistoricalSource(
        dataset_artifact_id="artifact-1",
        input_set_id="input-1",
        ordinal=0,
        retailer_id="walmart_us",
        adapter_id="historical_metricscart_search_monitor_csv",
        source_name="history.csv",
        source_format="metricscart_search_monitor_csv",
        storage_uri="s3://raw/history.csv",
        checksum=hashlib.sha256(body).hexdigest(),
        row_count=3,
    )
    reader = S3HistoricalCSVReader(bucket="raw", client=Client())

    batches = [batch async for batch in reader.iter_batches(source, batch_size=2)]

    assert [len(batch) for batch in batches] == [2, 1]
    assert batches[1][0]["Retailer Product Id"] == "3"
