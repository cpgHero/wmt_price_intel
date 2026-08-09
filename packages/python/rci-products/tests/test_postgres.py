from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from rci_db import DatabaseProbe
from rci_products import (
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
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us")
    contexts = [
        ProductDetailRequestContext(
            product_id=retailer_product_id,
            zipcode=zipcode,
            store=store,
            fulfillment_type="pickup",
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

        cache_run = await repository.create_run(max_credits=2)
        cleanup_run_ids.append(cache_run.id)
        cached = await repository.enqueue(cache_run.id, product, endpoint, contexts[0])
        assert cached.cached is True
        assert cached.snapshot_id is not None
        assert (await repository.product_document(product.id))["identity"]["brand"] == "Lay's"

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
