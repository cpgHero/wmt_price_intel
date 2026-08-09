from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import polars as pl

from rci_analytics.classification import OfferClassifier
from rci_analytics.models import MatchRecord
from rci_analytics.normalization import CanonicalOfferNormalizer, RetailerIdentityMap
from rci_analytics.parquet import InMemoryDatasetStore, ParquetDatasetWriter
from rci_analytics.product_pack import ProductPackLoader
from rci_collections import InMemoryCollectionRepository
from rci_collections.models import CollectionPlan, CostEstimate

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


async def test_normalized_and_classified_parquet_artifacts_are_readable_and_immutable() -> None:
    pack = ProductPackLoader(REPOSITORY_ROOT).load("fresh_strawberries")
    normalizer = CanonicalOfferNormalizer(
        RetailerIdentityMap.from_catalog(REPOSITORY_ROOT / "config" / "retailer-catalog.json")
    )
    offers = normalizer.normalize_many(
        [
            {
                "retailer_id": "walmart_us",
                "retailer_product_id": "44391605",
                "title": "Fresh Strawberries, 1 lb",
                "price": "2.38",
                "zipcode": "00123",
                "store_number": "0007",
                "stock_availability": True,
            },
            {
                "retailer_id": "walmart_us",
                "retailer_product_id": "0002",
                "title": "Frozen Strawberries, 1 lb",
                "price": "2.99",
                "zipcode": "00123",
                "store_number": "0007",
                "stock_availability": True,
            },
        ]
    )
    classified = OfferClassifier(pack).classify_many(offers)
    store = InMemoryDatasetStore()
    writer = ParquetDatasetWriter(store)

    normalized_artifact = await writer.write_normalized(
        offers, run_id="run-compact", retailer_id="walmart_us"
    )
    classified_artifact = await writer.write_classified(
        classified, run_id="run-compact", retailer_id="walmart_us"
    )

    assert normalized_artifact.row_count == 2
    assert classified_artifact.row_count == 2
    assert normalized_artifact.storage_uri.endswith(".parquet")
    assert classified_artifact.artifact_type == "classified_offers"
    frames = [pl.read_parquet(value) for value in store.objects.values()]
    assert {frame.height for frame in frames} == {2}
    classified_frame = next(frame for frame in frames if "in_scope" in frame.columns)
    assert classified_frame["in_scope"].to_list() == [True, False]


async def test_dataset_artifact_can_be_registered_against_collection_run() -> None:
    repository = InMemoryCollectionRepository()
    definition = await repository.publish_definition(
        {"id": "artifact-test", "name": "Artifact Test"}, "f" * 64
    )
    run = await repository.create_run(
        definition,
        CollectionPlan(
            estimate=CostEstimate(
                definition_id=definition.id,
                retailers=(),
                estimated_total_pages=0,
                estimated_total_credits=0,
            ),
            initial_tasks=(),
        ),
    )
    store = InMemoryDatasetStore()
    artifact = await ParquetDatasetWriter(store).write_normalized(
        [
            CanonicalOfferNormalizer(
                RetailerIdentityMap.from_catalog(
                    REPOSITORY_ROOT / "config" / "retailer-catalog.json"
                )
            ).normalize(
                {
                    "retailer_id": "walmart_us",
                    "retailer_product_id": "0001",
                    "title": "Fresh Strawberries, 1 lb",
                    "price": "2.38",
                    "zipcode": "00123",
                }
            )
        ],
        run_id=run.id,
        retailer_id="walmart_us",
    )

    assert await repository.record_artifact(run.id, artifact) == artifact.storage_uri
    assert await repository.record_artifact(run.id, artifact) == artifact.storage_uri


async def test_match_parquet_infers_sparse_optional_fields_across_the_full_batch() -> None:
    store = InMemoryDatasetStore()
    matches = [
        MatchRecord(
            profile_id="strict" if index < 100 else "proximity",
            competitor_id="aldi_us",
            geography_key=f"zip-{index:05d}",
            benchmark_offer_id=f"benchmark-{index}",
            competitor_offer_id=f"competitor-{index}",
            attributes={"weight_lb": 1.0},
            comparison_metric="price",
            benchmark_value=Decimal("4.97"),
            competitor_value=Decimal("4.49"),
            gap=Decimal("0.48"),
            winner="competitor",
            distance_miles=None if index < 100 else 0.270174,
        )
        for index in range(101)
    ]

    artifact = await ParquetDatasetWriter(store).write_matches(
        matches,
        run_id="run-sparse-distance",
        retailer_id="aldi_us",
    )

    frame = pl.read_parquet(store.objects[artifact.storage_uri.removeprefix("s3://test-datasets/")])
    assert frame.height == 101
    assert frame["distance_miles"].tail(1).item() == 0.270174


def test_core_engine_has_no_product_pack_id_branches() -> None:
    source_root = REPOSITORY_ROOT / "packages" / "python" / "rci-analytics" / "src"
    source = "\n".join(path.read_text() for path in source_root.rglob("*.py"))
    assert "fresh_strawberries" not in source
