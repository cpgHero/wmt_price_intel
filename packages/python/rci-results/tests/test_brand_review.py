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

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


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
            product_pack_version="1.2.0",
            schema_version="2.0.0",
            checksum="a" * 64,
            result={
                "benchmark_retailer": "walmart_us",
                "competitors": ["aldi_us"],
                "assortment_analysis": {
                    "retailers": [
                        {
                            "retailer": "walmart_us",
                            "brands": [
                                {
                                    "brand": "Great Value",
                                    "distinct_products": 4,
                                    "observed_locations": 80,
                                    "observed_zipcodes": 75,
                                    "location_share": 0.8,
                                },
                                {
                                    "brand": "Hiland Dairy",
                                    "distinct_products": 3,
                                    "observed_locations": 14,
                                    "observed_zipcodes": 12,
                                    "location_share": 0.14,
                                },
                            ],
                        },
                        {
                            "retailer": "aldi_us",
                            "brands": [
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
    assert great_value["observed_zipcodes"] == 22
    assert great_value["location_share"] == 0
    assert great_value["distribution_tier"] == "unknown"
    assert great_value["distribution_evidence"] == "pdp_identity_joined_to_matched_search"
    assert friendly_farms["distribution_evidence"] == "search_brand_field"
