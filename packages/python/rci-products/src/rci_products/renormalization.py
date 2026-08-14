"""Zero-credit, versioned re-normalization of immutable Product Details payloads."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import cast

from rci_products.adapters import MetricsCartProductDetailAdapter
from rci_products.models import (
    PRODUCT_DETAIL_NORMALIZER_VERSION,
    JsonObject,
    ProductDetailNormalizationCandidate,
)
from rci_products.repository import ProductDetailNormalizationRepository
from rci_products.storage import ProductDetailRawObjectReader

logger = logging.getLogger(__name__)


class ProductDetailRenormalizationWorker:
    """Rebuild derived PDP evidence without calling or billing the provider."""

    def __init__(
        self,
        repository: ProductDetailNormalizationRepository,
        reader: ProductDetailRawObjectReader,
        *,
        worker_id: str,
        claim_limit: int = 8,
        lease_seconds: int = 300,
        retry_delay_seconds: float = 30,
        normalizer_version: str = PRODUCT_DETAIL_NORMALIZER_VERSION,
    ) -> None:
        self._repository = repository
        self._reader = reader
        self._worker_id = worker_id
        self._claim_limit = claim_limit
        self._lease_seconds = lease_seconds
        self._retry_delay_seconds = retry_delay_seconds
        self._normalizer_version = normalizer_version

    async def run_once(self) -> int:
        candidates = await self._repository.claim_normalizations(
            self._worker_id,
            normalizer_version=self._normalizer_version,
            limit=self._claim_limit,
            lease_seconds=self._lease_seconds,
        )
        await asyncio.gather(*(self._execute(candidate) for candidate in candidates))
        return len(candidates)

    async def _execute(self, candidate: ProductDetailNormalizationCandidate) -> None:
        try:
            body = await self._reader.get_response(
                candidate.raw_storage_uri,
                expected_checksum=candidate.raw_checksum,
            )
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError("Product Details raw response is not a JSON object")
            normalized = MetricsCartProductDetailAdapter(candidate.endpoint).normalize(
                cast(JsonObject, value),
                candidate.context,
            )
            await self._repository.record_normalization(
                candidate,
                self._worker_id,
                normalized,
            )
            logger.info(
                "Product Details raw response re-normalized",
                extra={
                    "event": "product_detail_renormalized",
                    "snapshot_id": candidate.snapshot_id,
                    "retailer_id": candidate.retailer_id,
                    "normalizer_version": candidate.normalizer_version,
                    "source_field_count": len(normalized.source_field_inventory),
                    "unmapped_source_field_count": len(normalized.unmapped_source_fields),
                    "billable_credits": 0,
                },
            )
        except Exception as exc:
            await self._repository.fail_normalization(
                candidate,
                self._worker_id,
                f"{type(exc).__name__}: {exc}",
                retry_delay_seconds=self._retry_delay_seconds,
            )
            logger.warning(
                "Product Details re-normalization failed",
                extra={
                    "event": "product_detail_renormalization_failed",
                    "snapshot_id": candidate.snapshot_id,
                    "retailer_id": candidate.retailer_id,
                    "normalizer_version": candidate.normalizer_version,
                    "billable_credits": 0,
                },
            )
