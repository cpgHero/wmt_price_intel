from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rci_products import (
    PRODUCT_DETAIL_NORMALIZER_VERSION,
    ProductDetailCatalog,
    ProductDetailNormalizationCandidate,
    ProductDetailNormalizationRecord,
    ProductDetailRenormalizationWorker,
    ProductDetailRequestContext,
)
from rci_products.models import NormalizedProductDetail, sha256_document

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class RecordingRepository:
    candidates: list[ProductDetailNormalizationCandidate]
    normalized: list[NormalizedProductDetail] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    async def claim_normalizations(self, _worker_id: str, **_kwargs):
        claimed, self.candidates = self.candidates, []
        return claimed

    async def record_normalization(self, candidate, _worker_id, normalized):
        self.normalized.append(normalized)
        document = normalized.contract_document()
        return ProductDetailNormalizationRecord(
            id=candidate.id,
            snapshot_id=candidate.snapshot_id,
            normalizer_version=candidate.normalizer_version,
            document=document,
            document_checksum=sha256_document(document),
        )

    async def fail_normalization(
        self, _candidate, _worker_id, message, *, retry_delay_seconds: float
    ):
        assert retry_delay_seconds >= 0
        self.failures.append(message)

    async def normalization_audit(self, normalizer_version: str):
        return {"normalizer_version": normalizer_version}


@dataclass
class StaticReader:
    body: bytes
    calls: int = 0

    async def get_response(self, _storage_uri: str, *, expected_checksum: str) -> bytes:
        assert expected_checksum == "a" * 64
        self.calls += 1
        return self.body


def _candidate() -> ProductDetailNormalizationCandidate:
    return ProductDetailNormalizationCandidate(
        id="00000000-0000-0000-0000-000000000101",
        snapshot_id="00000000-0000-0000-0000-000000000102",
        normalizer_version=PRODUCT_DETAIL_NORMALIZER_VERSION,
        canonical_product_db_id="00000000-0000-0000-0000-000000000103",
        canonical_product_id="walmart_us:677669806",
        retailer_id="walmart_us",
        raw_storage_uri="s3://artifacts/raw/pdp.json.gz",
        raw_checksum="a" * 64,
        endpoint=ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us"),
        context=ProductDetailRequestContext(
            product_id="677669806",
            zipcode="90020",
            store="2464",
            fulfillment_type="pickup",
        ),
        attempt_count=1,
    )


async def test_worker_renormalizes_retained_raw_payload_without_provider_call() -> None:
    payload = (
        REPOSITORY_ROOT / "fixtures/api_samples/metricscart_pdp_walmart_200.json"
    ).read_bytes()
    repository = RecordingRepository([_candidate()])
    reader = StaticReader(payload)
    worker = ProductDetailRenormalizationWorker(
        repository,
        reader,
        worker_id="normalizer-a",
    )

    assert await worker.run_once() == 1
    assert reader.calls == 1
    assert repository.failures == []
    assert len(repository.normalized) == 1
    assert repository.normalized[0].seller == "Walmart.com"
    assert repository.normalized[0].demand["weekly_sales_volume"] == 10000
    assert await worker.run_once() == 0


async def test_worker_records_invalid_raw_payload_as_retryable_failure() -> None:
    repository = RecordingRepository([_candidate()])
    worker = ProductDetailRenormalizationWorker(
        repository,
        StaticReader(json.dumps(["not", "an", "object"]).encode()),
        worker_id="normalizer-a",
        retry_delay_seconds=1,
    )

    assert await worker.run_once() == 1
    assert repository.normalized == []
    assert "not a JSON object" in repository.failures[0]
