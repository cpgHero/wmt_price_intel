from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_db import DatabaseProbe
from rci_products import (
    PRODUCT_DETAIL_NORMALIZER_VERSION,
    PostgresProductDetailRepository,
    ProductDetailBudgetExceeded,
    ProductDetailCatalog,
    ProductDetailFetchResult,
    ProductDetailRawArtifact,
    ProductDetailRequestContext,
    source_context,
)
from rci_products.adapters import MetricsCartProductDetailAdapter

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Product Details Postgres integration",
)
async def test_postgres_queue_cache_budget_and_identity_are_replica_safe() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    repository = PostgresProductDetailRepository(database.engine, REPOSITORY_ROOT)
    unique = uuid4().hex
    retailer_product_id = f"pdp-test-{unique}"
    product = await repository.upsert_serp_product(
        retailer_id="walmart_us",
        retailer_product_id=retailer_product_id,
        name="SERP test product",
        brand=None,
        url=f"https://www.walmart.com/ip/{retailer_product_id}",
        image_primary=None,
        identifiers={"item_id": retailer_product_id},
        context=source_context(
            source="serp",
            observed_at=datetime.now(UTC),
            zipcode="00501",
            store_number="2464",
            fulfillment_type="pickup",
        ),
    )
    endpoint = replace(
        ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us"),
        fixed_params=(("fulfillment_type", "pickup"),),
    )
    contexts = [
        ProductDetailRequestContext(
            product_id=retailer_product_id,
            zipcode=zipcode,
            store=store,
            fulfillment_type="SFS",
        )
        for zipcode, store in (("00501", "2464"), ("90020", "2465"))
    ]
    run = await repository.create_run(max_credits=4)
    cleanup_run_ids = [run.id]
    payload = json.loads(
        (REPOSITORY_ROOT / "fixtures/api_samples/metricscart_pdp_walmart_200.json").read_text()
    )
    payload["retailer_product_id"] = retailer_product_id
    payload["product_identifiers"]["item_id"] = retailer_product_id
    payload["url"] = f"https://www.walmart.com/ip/{retailer_product_id}"
    try:
        await asyncio.gather(
            *(repository.enqueue(run.id, product, endpoint, context) for context in contexts)
        )
        claim_sets = await asyncio.gather(
            repository.claim("pdp-worker-a", limit=2, lease_seconds=30),
            repository.claim("pdp-worker-b", limit=2, lease_seconds=30),
        )
        claimed = [job for jobs in claim_sets for job in jobs]
        assert len(claimed) == 2
        assert len({job.id for job in claimed}) == 2
        assert all(job.endpoint.fixed() == {"fulfillment_type": "pickup"} for job in claimed)
        assert all(
            MetricsCartProductDetailAdapter(job.endpoint)
            .build_request(job.context)
            .params["fulfillment_type"]
            == "pickup"
            for job in claimed
        )

        for job in claimed:
            normalized = MetricsCartProductDetailAdapter(job.endpoint).normalize(
                payload, job.context
            )
            await repository.record_fetch(
                job,
                "pdp-worker-a" if job in claim_sets[0] else "pdp-worker-b",
                ProductDetailFetchResult(
                    observed_at=datetime.now(UTC),
                    http_status=200,
                    billable=True,
                    credits=2,
                    raw_artifact=ProductDetailRawArtifact(
                        artifact_id=f"raw-{job.id}",
                        storage_uri=f"s3://test/pdp/{job.id}.json.gz",
                        checksum="c" * 64,
                        byte_size=1,
                        metadata={},
                    ),
                    normalized=normalized,
                ),
                cache_ttl_seconds=3600,
            )
        completed = await repository.get_run(run.id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.actual_credits == 4
        audit = await repository.run_audit(run.id)
        assert audit is not None
        assert audit["planned_calls"] == 2
        assert audit["succeeded_calls"] == 2
        assert audit["failed_calls"] == 0
        assert audit["http_status_counts"] == {"200": 2}
        assert audit["actual_credits"] == 4
        assert {row["request_context"]["zipcode"] for row in audit["calls"]} == {
            "00501",
            "90020",
        }
        assert all(row["snapshot_id"] for row in audit["calls"])
        assert all(row["identity_evidence"]["name"] for row in audit["calls"])
        async with database.engine.connect() as connection:
            normalization_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM product_detail_normalization n "
                            "JOIN product_detail_snapshot s "
                            "ON s.id = n.product_detail_snapshot_id "
                            "JOIN product_detail_job j ON j.id = s.product_detail_job_id "
                            "WHERE j.enrichment_run_id::text = :run_id "
                            "AND n.normalizer_version = :normalizer_version "
                            "AND n.status = 'succeeded'"
                        ),
                        {
                            "run_id": run.id,
                            "normalizer_version": PRODUCT_DETAIL_NORMALIZER_VERSION,
                        },
                    )
                ).scalar_one()
            )
        assert normalization_count == 2

        cache_run = await repository.create_run(max_credits=2)
        cleanup_run_ids.append(cache_run.id)
        cached = await repository.enqueue(cache_run.id, product, endpoint, contexts[0])
        assert cached.cached is True
        assert cached.snapshot_id is not None
        product_document = await repository.product_document(product.id)
        assert product_document["identity"]["brand"] == "Lay's"
        assert product_document["identity"]["seller"] == "Walmart.com"

        budget_run = await repository.create_run(max_credits=2)
        cleanup_run_ids.append(budget_run.id)
        uncached_contexts = [
            ProductDetailRequestContext(
                product_id=retailer_product_id,
                zipcode=zipcode,
                store=store,
                fulfillment_type="pickup",
            )
            for zipcode, store in (("00502", "3464"), ("90021", "3465"))
        ]
        budget_results = await asyncio.gather(
            *(
                repository.enqueue(budget_run.id, product, endpoint, value)
                for value in uncached_contexts
            ),
            return_exceptions=True,
        )
        assert sum(not isinstance(value, Exception) for value in budget_results) == 1
        assert sum(isinstance(value, ProductDetailBudgetExceeded) for value in budget_results) == 1
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM audit_event "
                    "WHERE entity_type = 'product_detail_snapshot' AND entity_id IN ("
                    "SELECT snapshot.id::text FROM product_detail_snapshot snapshot "
                    "JOIN product_detail_job job ON job.id = snapshot.product_detail_job_id "
                    "WHERE job.enrichment_run_id = ANY(CAST(:run_ids AS uuid[])))"
                ),
                {"run_ids": cleanup_run_ids},
            )
            await connection.execute(
                text("DELETE FROM audit_event WHERE entity_id = ANY(CAST(:entity_ids AS text[]))"),
                {"entity_ids": cleanup_run_ids},
            )
            await connection.execute(
                text(
                    "DELETE FROM product_detail_enrichment_run "
                    "WHERE id = ANY(CAST(:run_ids AS uuid[]))"
                ),
                {"run_ids": cleanup_run_ids},
            )
            await connection.execute(
                text("DELETE FROM canonical_product WHERE id::text = :product_id"),
                {"product_id": product.id},
            )
        await database.dispose()


@pytest.mark.skipif(
    not os.getenv("RCI_TEST_DATABASE_URL"),
    reason="set RCI_TEST_DATABASE_URL to run Product Details Postgres integration",
)
async def test_postgres_queue_claims_one_job_per_retailer_before_second_jobs() -> None:
    database = DatabaseProbe(os.environ["RCI_TEST_DATABASE_URL"])
    repository = PostgresProductDetailRepository(database.engine, REPOSITORY_ROOT)
    unique = uuid4().hex
    run = await repository.create_run(max_credits=10)
    products = []
    try:
        for retailer_id in ("walmart_us", "kroger_us", "target_us"):
            endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get(retailer_id)
            for index in range(2):
                retailer_product_id = f"fair-{unique}-{retailer_id}-{index}"
                product = await repository.upsert_serp_product(
                    retailer_id=retailer_id,
                    retailer_product_id=retailer_product_id,
                    name=f"Fair queue {retailer_id} {index}",
                    brand=None,
                    url=f"https://example.test/{retailer_product_id}",
                    image_primary=None,
                    identifiers={"product_id": retailer_product_id},
                    context={"source": "queue_fairness_test"},
                )
                products.append(product)
                await repository.enqueue(
                    run.id,
                    product,
                    endpoint,
                    ProductDetailRequestContext(
                        product_id=retailer_product_id,
                        zipcode=f"4308{index}",
                        store=f"store-{index}",
                        fulfillment_type="pickup",
                        url=(
                            f"https://example.test/{retailer_product_id}"
                            if retailer_id == "target_us"
                            else None
                        ),
                    ),
                )

        claimed = await repository.claim("fair-worker", limit=3, lease_seconds=30)

        assert len(claimed) == 3
        assert {job.retailer_id for job in claimed} == {
            "walmart_us",
            "kroger_us",
            "target_us",
        }
    finally:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM audit_event WHERE entity_id = :run_id"),
                {"run_id": run.id},
            )
            await connection.execute(
                text("DELETE FROM product_detail_enrichment_run WHERE id::text = :run_id"),
                {"run_id": run.id},
            )
            await connection.execute(
                text("DELETE FROM canonical_product WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [product.id for product in products]},
            )
        await database.dispose()
