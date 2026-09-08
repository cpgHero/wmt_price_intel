from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from rci_analytics.product_pack import ProductPackLoader
from rci_contracts import validate_instance
from rci_results.brand_review import (
    BrandDecisionCommand,
    BrandReviewService,
    BrandRevisionConflictError,
    InMemoryBrandReviewRepository,
)
from rci_results.models import AnalysisRecord
from rci_retailer_packs import GovernedBrandResolver

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

STORE_SEARCH_DISTRIBUTION_CONTRACT = {
    "version": "1.0.0",
    "basis": "positive_price_store_search_result",
    "grain": "retailer_product_id_x_store_id",
    "deduplication": "distinct_store_id_per_product",
    "price_rule": "price_gt_zero",
    "inventory_claim": False,
    "stock_status_used": False,
    "sponsorship_used": False,
}


class FakePackLoader:
    async def load(self, pack_id: str, version: str):
        pack = ProductPackLoader(REPOSITORY_ROOT).load(pack_id)
        assert pack.version == version
        return pack


class FakeResults:
    def __init__(self) -> None:
        self.analysis = AnalysisRecord(
            id="00000000-0000-0000-0000-000000000511",
            analysis_run_id="00000000-0000-0000-0000-000000000411",
            analysis_id="fresh-milk-example",
            collection_run_id="00000000-0000-0000-0000-000000000311",
            status="succeeded",
            product_pack_id="fresh_fluid_milk",
            product_pack_version="1.6.0",
            schema_version="2.0.0",
            checksum="a" * 64,
            result={
                "benchmark_retailer": "walmart_us",
                "competitors": ["aldi_us"],
                "assortment_analysis": {
                    "distribution_contract": STORE_SEARCH_DISTRIBUTION_CONTRACT,
                    "retailers": [
                        {
                            "retailer": "walmart_us",
                            "distribution_store_count": 100,
                            "service_area_presence_count": 0,
                            "brands": [
                                {
                                    "brand": "Great Value",
                                    "distinct_products": 4,
                                    "observed_locations": 80,
                                    "observed_zipcodes": 75,
                                    "distribution_store_count": 80,
                                    "service_area_presence_count": 0,
                                    "location_share": 0.8,
                                },
                                {
                                    "brand": "Hiland Dairy",
                                    "distinct_products": 3,
                                    "observed_locations": 14,
                                    "observed_zipcodes": 12,
                                    "distribution_store_count": 14,
                                    "service_area_presence_count": 0,
                                    "location_share": 0.14,
                                },
                                {
                                    "brand": "Mayfield",
                                    "distinct_products": 2,
                                    "observed_locations": 10,
                                    "observed_zipcodes": 9,
                                    "distribution_store_count": 10,
                                    "service_area_presence_count": 0,
                                    "location_share": 0.1,
                                },
                            ],
                        },
                        {
                            "retailer": "aldi_us",
                            "distribution_store_count": 50,
                            "service_area_presence_count": 0,
                            "brands": [
                                {
                                    "brand": "Friendly Farms",
                                    "distinct_products": 3,
                                    "observed_locations": 40,
                                    "observed_zipcodes": 38,
                                    "distribution_store_count": 40,
                                    "service_area_presence_count": 0,
                                    "location_share": 0.8,
                                }
                            ],
                        },
                    ],
                },
            },
            created_at=datetime.now(UTC),
        )

    async def get(self, _identifier: str) -> AnalysisRecord:
        return self.analysis

    async def latest_publication(self, _identifier: str):
        return None


class PublishedLegacyResults(FakeResults):
    async def latest_publication(self, _identifier: str):
        return SimpleNamespace(
            result={
                "benchmark_retailer": "walmart_us",
                "competitors": ["aldi_us"],
            },
            presentation_context={
                "assortment_analysis": {
                    "retailers": [
                        {
                            "retailer": "walmart_us",
                            "observed_locations": 100,
                            "observed_zipcodes": 100,
                            "top_brands": [],
                        },
                        {
                            "retailer": "aldi_us",
                            "observed_locations": 50,
                            "observed_zipcodes": 50,
                            "top_brands": [
                                {
                                    "brand": "Friendly Farms",
                                    "distinct_products": 3,
                                    "observed_locations": 40,
                                    "observed_zipcodes": 38,
                                    "location_share": 0.8,
                                }
                            ],
                        },
                    ]
                },
                "product_highlights": [
                    {
                        "canonical_product_id": "walmart_us:w-1",
                        "brand": "Great value",
                        "name": "Great Value Whole Milk",
                        "image_url": "https://example.com/w-1.png",
                    },
                    {
                        "canonical_product_id": "walmart_us:w-2",
                        "brand": "Great Value",
                        "name": "Great Value 2% Milk",
                        "image_url": "https://example.com/w-2.png",
                    },
                ],
                "match_candidates": [
                    {
                        "competitor": "aldi_us",
                        "benchmark_product_id": "w-1",
                        "competitor_product_id": "a-1",
                        "geographies": 22,
                    },
                    {
                        "competitor": "aldi_us",
                        "benchmark_product_id": "w-2",
                        "competitor_product_id": "a-2",
                        "geographies": 18,
                    },
                ],
            },
        )


@pytest.mark.asyncio
async def test_brand_workbench_stages_human_roles_without_immediate_reanalysis() -> None:
    repository = InMemoryBrandReviewRepository()
    service = BrandReviewService(  # type: ignore[arg-type]
        FakeResults(),
        repository,
        FakePackLoader(),
        retailer_names={"walmart_us": "Walmart", "aldi_us": "ALDI"},
        brand_resolver=GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )

    initial = await service.view("fresh-milk-example")
    validate_instance(
        REPOSITORY_ROOT, "brand-workbench.schema.json", initial, label="brand workbench"
    )
    assert initial["revision"] == 0
    hiland = next(row for row in initial["brands"] if row["display_brand"] == "Hiland Dairy")
    assert hiland["role"] == "regional"
    assert hiland["status"] == "suggested"
    assert hiland["distribution_tier"] == "concentrated"
    assert hiland["distribution_evidence"] == "positive_price_store_search_result"
    assert hiland["distribution_store_count"] == 14
    assert hiland["service_area_presence_count"] == 0
    mayfield = next(row for row in initial["brands"] if row["display_brand"] == "Mayfield")
    assert mayfield["role"] == "unclassified"
    assert mayfield["candidate_status"] == "candidate"
    assert mayfield["candidate_matches"][0]["canonical_brand_id"] == (
        "regional__mayfield_dairy_farms"
    )

    saved = await service.decide(
        "fresh-milk-example",
        BrandDecisionCommand(
            expected_revision=0,
            retailer_id="walmart_us",
            normalized_brand="hiland dairy",
            role="regional",
            decision="confirmed",
            reason="Confirmed regional dairy portfolio",
        ),
        actor="reviewer",
    )
    assert saved["revision"] == 1
    reviewed = await service.view("fresh-milk-example")
    hiland = next(row for row in reviewed["brands"] if row["display_brand"] == "Hiland Dairy")
    assert hiland["role"] == "regional"
    assert hiland["status"] == "confirmed"
    assert reviewed["future_application"] is None

    with pytest.raises(BrandRevisionConflictError):
        await service.decide(
            "fresh-milk-example",
            BrandDecisionCommand(
                expected_revision=0,
                retailer_id="walmart_us",
                normalized_brand="hiland dairy",
                role="national",
                decision="confirmed",
            ),
            actor="stale-reviewer",
        )

    reanalysis = await service.recompute(
        "fresh-milk-example",
        expected_revision=1,
        apply_to_future_runs=True,
        actor="reviewer",
    )
    assert reanalysis.status == "queued"
    future = await service.view("fresh-milk-example")
    assert future["future_application"]["revision"] == 1


@pytest.mark.asyncio
async def test_brand_workbench_persists_a_validated_canonical_mapping() -> None:
    repository = InMemoryBrandReviewRepository()
    service = BrandReviewService(  # type: ignore[arg-type]
        FakeResults(),
        repository,
        FakePackLoader(),
        retailer_names={"walmart_us": "Walmart", "aldi_us": "ALDI"},
        brand_resolver=GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )

    saved = await service.decide(
        "fresh-milk-example",
        BrandDecisionCommand(
            expected_revision=0,
            retailer_id="walmart_us",
            normalized_brand="mayfield",
            role="regional",
            decision="confirmed",
            canonical_brand_id="regional__mayfield_dairy_farms",
        ),
        actor="reviewer",
    )
    rules = await repository.rules(saved["revision_id"])
    view = await service.view("fresh-milk-example")
    mayfield = next(row for row in view["brands"] if row["display_brand"] == "Mayfield")

    assert rules[0].evidence["canonical_brand_id"] == "regional__mayfield_dairy_farms"
    assert rules[0].evidence["canonical_brand_name"] == "Mayfield Dairy Farms"
    assert mayfield["status"] == "confirmed"
    assert mayfield["candidate_status"] == "governed"
    assert mayfield["canonical_brand_name"] == "Mayfield Dairy Farms"


@pytest.mark.asyncio
async def test_brand_workbench_rejects_unoffered_or_role_mismatched_mappings() -> None:
    service = BrandReviewService(  # type: ignore[arg-type]
        FakeResults(),
        InMemoryBrandReviewRepository(),
        FakePackLoader(),
        brand_resolver=GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )

    with pytest.raises(ValueError, match="not an eligible candidate"):
        await service.decide(
            "fresh-milk-example",
            BrandDecisionCommand(
                expected_revision=0,
                retailer_id="walmart_us",
                normalized_brand="mayfield",
                role="regional",
                decision="confirmed",
                canonical_brand_id="national__fairlife",
            ),
            actor="reviewer",
        )
    with pytest.raises(ValueError, match="role must match"):
        await service.decide(
            "fresh-milk-example",
            BrandDecisionCommand(
                expected_revision=0,
                retailer_id="walmart_us",
                normalized_brand="mayfield",
                role="national",
                decision="confirmed",
                canonical_brand_id="regional__mayfield_dairy_farms",
            ),
            actor="reviewer",
        )


@pytest.mark.asyncio
async def test_brand_workbench_treats_explicit_zero_distribution_as_authoritative() -> None:
    results = FakeResults()
    retailer = results.analysis.result["assortment_analysis"]["retailers"][0]  # type: ignore[index]
    brand = retailer["brands"][1]
    brand["distribution_store_count"] = 0
    brand["service_area_presence_count"] = 0
    brand["distinct_products"] = 0
    brand["observed_locations"] = 4_510
    brand["observed_zipcodes"] = 0
    brand["location_share"] = 0.99

    service = BrandReviewService(  # type: ignore[arg-type]
        results,
        InMemoryBrandReviewRepository(),
        FakePackLoader(),
        retailer_names={"walmart_us": "Walmart", "aldi_us": "ALDI"},
        brand_resolver=GovernedBrandResolver.from_repository(REPOSITORY_ROOT),
    )

    view = await service.view("fresh-milk-example")
    validate_instance(
        REPOSITORY_ROOT, "brand-workbench.schema.json", view, label="zero verified brand workbench"
    )
    hiland = next(row for row in view["brands"] if row["display_brand"] == "Hiland Dairy")

    assert hiland["observed_products"] == 0
    assert hiland["observed_locations"] == 0
    assert hiland["observed_zipcodes"] == 0
    assert hiland["distribution_store_count"] == 0
    assert hiland["service_area_presence_count"] == 0
    assert hiland["location_share"] == 0
    assert hiland["distribution_evidence"] == "positive_price_store_search_result"
    assert hiland["distribution_tier"] == "unknown"


@pytest.mark.asyncio
async def test_brand_workbench_backfills_pdp_brands_from_legacy_publication_context() -> None:
    service = BrandReviewService(  # type: ignore[arg-type]
        PublishedLegacyResults(),
        InMemoryBrandReviewRepository(),
        FakePackLoader(),
        retailer_names={"walmart_us": "Walmart", "aldi_us": "ALDI"},
    )

    view = await service.view("fresh-milk-example")
    validate_instance(
        REPOSITORY_ROOT, "brand-workbench.schema.json", view, label="legacy brand workbench"
    )
    great_value = next(row for row in view["brands"] if row["normalized_brand"] == "great value")
    friendly_farms = next(
        row for row in view["brands"] if row["normalized_brand"] == "friendly farms"
    )

    assert great_value["role"] == "private_label"
    assert great_value["observed_products"] == 2
    assert great_value["observed_locations"] == 0
    assert great_value["observed_zipcodes"] == 0
    assert great_value["distribution_store_count"] == 0
    assert great_value["service_area_presence_count"] == 0
    assert great_value["location_share"] == 0
    assert great_value["distribution_tier"] == "unknown"
    assert great_value["distribution_evidence"] == "pdp_identity_only"
    assert friendly_farms["distribution_evidence"] == "search_brand_field"
