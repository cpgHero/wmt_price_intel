from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from rci_products import (
    InMemoryProductDetailRepository,
    ProductDetailBudgetExceeded,
    ProductDetailCatalog,
    ProductDetailFetchResult,
    ProductDetailRawArtifact,
    ProductDetailRequestContext,
    ProductDetailWorker,
    attach_product_identity,
    source_context,
)
from rci_products.adapters import MetricsCartProductDetailAdapter

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class FixtureFetcher:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    async def fetch(self, job):
        self.calls += 1
        normalized = MetricsCartProductDetailAdapter(job.endpoint).normalize(
            self.payload, job.context
        )
        return ProductDetailFetchResult(
            observed_at=datetime.now(UTC),
            http_status=200,
            billable=True,
            credits=job.credits_per_call,
            raw_artifact=ProductDetailRawArtifact(
                artifact_id="raw-test",
                storage_uri="s3://test/pdp.json.gz",
                checksum="b" * 64,
                byte_size=1,
                metadata={},
            ),
            normalized=normalized,
        )


async def _product(repository: InMemoryProductDetailRepository):
    return await repository.upsert_serp_product(
        retailer_id="walmart_us",
        retailer_product_id="677669806",
        name="SERP title",
        brand=None,
        url="https://www.walmart.com/ip/677669806",
        image_primary=None,
        identifiers={"item_id": "677669806"},
        context=source_context(
            source="serp",
            observed_at=datetime.now(UTC),
            zipcode="90020",
            store_number="2464",
            fulfillment_type="pickup",
        ),
    )


async def test_one_cached_pdp_enriches_all_linked_serp_observations_without_overwrite() -> None:
    import json

    repository = InMemoryProductDetailRepository(REPOSITORY_ROOT)
    product = await _product(repository)
    catalog = ProductDetailCatalog.from_path(REPOSITORY_ROOT)
    endpoint = catalog.get("walmart_us")
    context = ProductDetailRequestContext(
        product_id="677669806",
        zipcode="90020",
        store="2464",
        fulfillment_type="pickup",
    )
    run = await repository.create_run(max_credits=2)
    queued = await repository.enqueue(run.id, product, endpoint, context)
    assert queued.created is True
    payload = json.loads(
        (REPOSITORY_ROOT / "fixtures/api_samples/metricscart_pdp_walmart_200.json").read_text()
    )
    fetcher = FixtureFetcher(payload)
    worker = ProductDetailWorker(repository, fetcher, worker_id="worker-a")

    assert await worker.run_once() == 1
    assert fetcher.calls == 1
    completed = await repository.get_run(run.id)
    assert completed.planned_credits == 2
    assert completed.actual_credits == 2

    second_run = await repository.create_run(max_credits=2)
    cached = await repository.enqueue(second_run.id, product, endpoint, context)
    assert cached.cached is True
    assert cached.snapshot_id is not None
    assert await worker.run_once() == 0
    assert fetcher.calls == 1

    product_document = await repository.product_document(product.id)
    observations = [
        {
            "retailer_id": "walmart_us",
            "retailer_product_id": "677669806",
            "price": 4.12,
            "in_stock": True,
            "zipcode": "90020",
        },
        {
            "retailer_id": "walmart_us",
            "retailer_product_id": "677669806",
            "price": 4.39,
            "in_stock": False,
            "zipcode": "10001",
        },
    ]
    enriched = attach_product_identity(
        observations, product_document, snapshot_id=cached.snapshot_id
    )

    assert [row["price"] for row in enriched] == [4.12, 4.39]
    assert [row["in_stock"] for row in enriched] == [True, False]
    assert all(row["product_identity"]["brand"] == "Lay's" for row in enriched)
    assert product_document["identity"]["description_full"]


async def test_concurrent_enqueue_enforces_atomic_credit_ceiling() -> None:
    repository = InMemoryProductDetailRepository(REPOSITORY_ROOT)
    product = await _product(repository)
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us")
    run = await repository.create_run(max_credits=2)
    contexts = [
        ProductDetailRequestContext(
            product_id="677669806",
            zipcode=zipcode,
            store=store,
            fulfillment_type="pickup",
        )
        for zipcode, store in (("90020", "2464"), ("10001", "1234"))
    ]
    results = await asyncio.gather(
        *(repository.enqueue(run.id, product, endpoint, context) for context in contexts),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ProductDetailBudgetExceeded) for result in results) == 1
    assert (await repository.get_run(run.id)).planned_credits == 2


async def test_cancel_prevents_queued_jobs_from_being_claimed() -> None:
    repository = InMemoryProductDetailRepository(REPOSITORY_ROOT)
    product = await _product(repository)
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us")
    run = await repository.create_run(max_credits=2)
    await repository.enqueue(
        run.id,
        product,
        endpoint,
        ProductDetailRequestContext(
            product_id="677669806",
            zipcode="90020",
            store="2464",
            fulfillment_type="pickup",
        ),
    )

    assert await repository.cancel_run(run.id) == 1
    assert await repository.claim("worker-a", limit=1, lease_seconds=60) == []
