"""Durable worker for Search-first study population profiling."""

from __future__ import annotations

import logging
from pathlib import Path

from rci_analytics import CanonicalOfferNormalizer
from rci_analytics.normalization import RetailerIdentityMap
from rci_providers import MetricsCartAdapterRegistry
from rci_retailer_packs import GovernedBrandResolver
from rci_studies import (
    DiscoveryObservation,
    PostgresStudyRepository,
    StudyJob,
    profile_products,
)
from rci_worker.analysis import PostgresAnalysisQueue, S3RawPageReader

logger = logging.getLogger(__name__)


class StudyDiscoveryWorker:
    def __init__(
        self,
        *,
        repository_root: Path,
        repository: PostgresStudyRepository,
        page_repository: PostgresAnalysisQueue,
        raw_reader: S3RawPageReader,
        adapters: MetricsCartAdapterRegistry,
        worker_id: str,
        claim_limit: int = 1,
        lease_seconds: int = 600,
    ) -> None:
        self._root = repository_root
        self._repository = repository
        self._pages = page_repository
        self._reader = raw_reader
        self._adapters = adapters
        self._worker_id = worker_id
        self._claim_limit = claim_limit
        self._lease_seconds = lease_seconds

    async def run_once(self) -> int:
        materialized = await self._repository.materialize_profile_jobs()
        await self._repository.reconcile_enrichment()
        await self._repository.reconcile_product_pack_status()
        jobs = await self._repository.claim_jobs(
            self._worker_id,
            limit=self._claim_limit,
            lease_seconds=self._lease_seconds,
        )
        for job in jobs:
            try:
                if job.kind != "profile":
                    raise ValueError(f"unsupported study-discovery job kind {job.kind!r}")
                await self._profile(job)
            except Exception as exc:
                logger.exception(
                    "study discovery job failed",
                    extra={"event": "study_discovery_failed", "job_id": job.id},
                )
                await self._repository.fail_job(job, self._worker_id, str(exc))
        return materialized + len(jobs)

    async def _profile(self, job: StudyJob) -> None:
        study = await self._repository.get(job.study_id)
        if str(job.payload.get("query_plan_checksum")) != study.query_plan_checksum:
            raise ValueError("profile job references a stale query plan")
        run_id = str(job.payload["collection_run_id"])
        pages = await self._pages.pages(run_id)
        if not pages:
            raise ValueError("completed discovery collection has no successful Search pages")
        normalizer = CanonicalOfferNormalizer(
            RetailerIdentityMap.from_catalog(self._root / "config" / "retailer-catalog.json")
        )
        observations: list[DiscoveryObservation] = []
        for page in pages:
            payload = await self._reader.read(page)
            adapter = self._adapters.get(page.task.adapter_id)
            for result in adapter.extract_result_array(payload):
                try:
                    offer = normalizer.normalize(
                        {
                            **result,
                            **adapter.normalize_result(result, page.task),
                            "latitude": page.latitude,
                            "longitude": page.longitude,
                            "collected_at": page.collected_at.isoformat(),
                        }
                    )
                except ValueError:
                    continue
                raw_fulfillment = offer.raw.get("fulfillment_type")
                fulfillment = (
                    str(raw_fulfillment).strip()
                    if raw_fulfillment is not None and str(raw_fulfillment).strip()
                    else "pickup"
                    if offer.retailer_id in {"walmart_us", "aldi_us"}
                    else None
                )
                observations.append(
                    DiscoveryObservation(
                        retailer_id=offer.retailer_id,
                        retailer_product_id=offer.retailer_product_id,
                        title=offer.title,
                        brand=offer.brand,
                        price=offer.price,
                        zipcode=offer.zipcode,
                        store_number=offer.store_number,
                        url=offer.product_url,
                        image_url=offer.image_url,
                        source_artifact_id=page.task.raw_artifact_id,
                        identifiers={
                            "product_id": offer.retailer_product_id,
                            **(
                                dict(offer.raw["product_identifiers"])
                                if isinstance(offer.raw.get("product_identifiers"), dict)
                                else {}
                            ),
                        },
                        fulfillment_type=fulfillment,
                    )
                )
        profile = profile_products(
            observations,
            query_plan=study.query_plan,
            brand_resolver=GovernedBrandResolver.from_repository(self._root),
        )
        await self._repository.complete_profile(job, self._worker_id, profile)
