#!/usr/bin/env python3
"""Audit Spring Valley live Search evidence without launching paid PDP or AI work."""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

from botocore.config import Config
from sqlalchemy import text

from rci_analytics import CanonicalOfferNormalizer, CatalogProductPackLoader, OfferClassifier
from rci_analytics.normalization import RetailerIdentityMap
from rci_collections.models import QueueTask
from rci_core import AppSettings
from rci_db import DatabaseProbe
from rci_product_packs import PostgresProductPackCatalog
from rci_products import (
    MetricsCartProductDetailAdapter,
    PostgresProductDetailRepository,
    ProductDetailCatalog,
    plan_product_detail_candidates,
)
from rci_providers import MetricsCartAdapterRegistry

ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"
CANONICAL_FIELDS = (
    "name",
    "retailer_product_id",
    "brand",
    "price",
    "price_regular",
    "price_discounted",
    "is_sponsored",
    "url",
    "image_primary",
    "product_identifiers",
)
SELLER_FIELDS = ("seller", "seller_name", "sold_by", "merchant", "merchant_name")
USD_PER_METRICSCART_CREDIT = Decimal("0.002")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", action="append", required=True, dest="run_ids")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--product-pack-version", default="1.0.2")
    parser.add_argument(
        "--retailer-id",
        action="append",
        dest="retailer_ids",
        help="Restrict audit and paid launch to one or more retailer IDs.",
    )
    parser.add_argument(
        "--repository-root", type=Path, default=Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd()))
    )
    parser.add_argument(
        "--max-spend-usd",
        type=Decimal,
        help=(
            "Hard paid-call ceiling in USD. MetricsCart credits are converted at $0.002 "
            "per credit; this is required with --confirm-paid-calls."
        ),
    )
    parser.add_argument(
        "--confirm-paid-calls",
        action="store_true",
        help="Create a durable cache-aware PDP run after all audit gates pass.",
    )
    return parser.parse_args()


def _credit_ceiling(max_spend_usd: Decimal | None) -> int | None:
    if max_spend_usd is None:
        return None
    if not max_spend_usd.is_finite() or max_spend_usd <= 0:
        raise ValueError("PDP spend ceiling must be a positive finite USD amount")
    return int((max_spend_usd / USD_PER_METRICSCART_CREDIT).to_integral_value(ROUND_FLOOR))


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _queue_task(row: dict[str, Any]) -> QueueTask:
    return QueueTask(
        id=str(row["id"]),
        collection_run_id=str(row["collection_run_id"]),
        retailer_id=str(row["retailer_id"]),
        retailer_location_id=(
            str(row["retailer_location_id"]) if row["retailer_location_id"] else None
        ),
        adapter_id=str(row["adapter_id"]),
        location_scope_key=str(row["location_scope_key"]),
        zipcode=str(row["zipcode"]),
        store_number=str(row["store_number"]) if row["store_number"] is not None else None,
        page_number=int(row["page_number"]),
        max_pages=int(row["max_pages"]),
        stop_on_empty=bool(row["stop_on_empty"]),
        stop_on_short_page=bool(row["stop_on_short_page"]),
        credits_per_success=int(row["credits_per_success"]),
        request_payload=dict(row["request_payload"]),
        request_fingerprint=str(row["request_fingerprint"]),
        status=str(row["status"]),
        priority=int(row["priority"]),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        available_at=row["available_at"],
        locked_by=str(row["locked_by"]) if row["locked_by"] is not None else None,
        lease_expires_at=row["lease_expires_at"],
        created_at=row["created_at"],
        raw_artifact_id=(str(row["raw_artifact_id"]) if row["raw_artifact_id"] else None),
        http_status=int(row["http_status"]) if row["http_status"] is not None else None,
        result_count=int(row["result_count"]) if row["result_count"] is not None else None,
        failure_class=str(row["failure_class"]) if row["failure_class"] is not None else None,
        billable_credits=int(row["billable_credits"]),
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        is_preflight=bool(row["is_preflight"]),
    )


def _seller(result: dict[str, Any]) -> str | None:
    for field in SELLER_FIELDS:
        value = result.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _fulfillment(retailer_id: str, result: dict[str, Any]) -> str | None:
    for field in ("fulfillment_type", "shipping_type", "shopping_type"):
        value = result.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    if retailer_id in {"walmart_us", "target_us", "sams_club_us", "meijer_us"}:
        return "pickup"
    return None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    credit_ceiling = _credit_ceiling(args.max_spend_usd)
    if args.confirm_paid_calls and credit_ceiling is None:
        raise ValueError("--max-spend-usd is required with --confirm-paid-calls")
    root = args.repository_root.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = AppSettings.from_env()
    database = DatabaseProbe(settings.database_url)
    try:
        import boto3  # type: ignore[import-untyped]

        client = boto3.client(
            "s3",
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT") or None,
            region_name=os.getenv("OBJECT_STORAGE_REGION") or None,
            aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY") or None,
            config=Config(
                s3={
                    "addressing_style": (
                        "path"
                        if _enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True)
                        else "virtual"
                    )
                }
            ),
        )
        bucket = os.environ["OBJECT_STORAGE_BUCKET"]
        async with database.engine.connect() as connection:
            task_rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT t.*, da.storage_uri, da.checksum,
                                   da.created_at AS artifact_created_at,
                                   l.latitude, l.longitude
                            FROM collection_task t
                            LEFT JOIN dataset_artifact da ON da.id = t.raw_artifact_id
                            LEFT JOIN retailer_location l ON l.id = t.retailer_location_id
                            WHERE t.collection_run_id::text = ANY(CAST(:run_ids AS text[]))
                            ORDER BY t.retailer_id, t.location_scope_key, t.page_number, t.id
                            """
                        ),
                        {"run_ids": list(args.run_ids)},
                    )
                )
                .mappings()
                .all()
            )

        adapters = MetricsCartAdapterRegistry.from_catalog(root / "config/retailer-catalog.json")
        normalizer = CanonicalOfferNormalizer(
            RetailerIdentityMap.from_catalog(root / "config/retailer-catalog.json")
        )
        pack = await CatalogProductPackLoader(
            root, PostgresProductPackCatalog(database.engine)
        ).load("vitamins_supplements", args.product_pack_version)
        classifier = OfferClassifier(pack)

        task_status: dict[str, Counter[str]] = defaultdict(Counter)
        http_status: dict[str, Counter[str]] = defaultdict(Counter)
        raw_field_counts: dict[str, Counter[str]] = defaultdict(Counter)
        canonical_coverage: dict[str, Counter[str]] = defaultdict(Counter)
        raw_seller_counts: dict[str, Counter[str]] = defaultdict(Counter)
        scope_reasons: dict[str, Counter[str]] = defaultdict(Counter)
        raw_result_count: Counter[str] = Counter()
        normalized_result_count: Counter[str] = Counter()
        positive_price_count: Counter[str] = Counter()
        sponsored_count: Counter[str] = Counter()
        unique_raw_products: dict[str, set[str]] = defaultdict(set)
        unique_scope_products: dict[str, set[str]] = defaultdict(set)
        keywords_by_product: dict[tuple[str, str], set[str]] = defaultdict(set)
        observations_by_product: dict[tuple[str, str], dict[str, Any]] = {}
        admitted_products: dict[tuple[str, str], dict[str, Any]] = {}
        checksum_failures: list[str] = []
        selected_retailers = set(args.retailer_ids or [])

        for raw_row in task_rows:
            row = dict(raw_row)
            retailer_id = str(row["retailer_id"])
            if selected_retailers and retailer_id not in selected_retailers:
                continue
            status = str(row["status"])
            task_status[retailer_id][status] += 1
            if row["http_status"] is not None:
                http_status[retailer_id][str(row["http_status"])] += 1
            if not (
                status == "succeeded"
                and row["http_status"] is not None
                and 200 <= int(row["http_status"]) <= 299
                and row["storage_uri"]
            ):
                continue
            prefix = f"s3://{bucket}/"
            storage_uri = str(row["storage_uri"])
            if not storage_uri.startswith(prefix):
                raise ValueError(f"artifact belongs to unexpected bucket: {storage_uri}")
            response = client.get_object(Bucket=bucket, Key=storage_uri.removeprefix(prefix))
            body = response["Body"].read()
            if hashlib.sha256(body).hexdigest() != str(row["checksum"]):
                checksum_failures.append(str(row["id"]))
                continue
            payload = json.loads(gzip.decompress(body))
            task = _queue_task(row)
            adapter = adapters.get(task.adapter_id)
            results = adapter.extract_result_array(payload)
            keyword = str(task.request_payload.get("keyword") or "")
            for result in results:
                raw_result_count[retailer_id] += 1
                raw_field_counts[retailer_id].update(str(field) for field in result)
                for field in CANONICAL_FIELDS:
                    if adapter._field(result, field) not in (None, ""):
                        canonical_coverage[retailer_id][field] += 1
                observed_seller = _seller(result)
                raw_seller_counts[retailer_id][observed_seller or "<missing>"] += 1
                normalized_source = {
                    **result,
                    **adapter.normalize_result(result, task),
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "collected_at": row["artifact_created_at"].isoformat(),
                }
                try:
                    offer = normalizer.normalize(normalized_source)
                except ValueError as exc:
                    scope_reasons[retailer_id][f"normalization failed: {exc}"] += 1
                    continue
                normalized_result_count[retailer_id] += 1
                unique_raw_products[retailer_id].add(offer.retailer_product_id)
                keywords_by_product[(retailer_id, offer.retailer_product_id)].add(keyword)
                if offer.price is not None and offer.price > 0:
                    positive_price_count[retailer_id] += 1
                if offer.is_sponsored:
                    sponsored_count[retailer_id] += 1
                classified = classifier.classify(offer)
                scope_reasons[retailer_id][classified.scope_reason or "admitted"] += 1
                if not classified.in_scope:
                    continue
                unique_scope_products[retailer_id].add(offer.retailer_product_id)
                observation = {
                    **offer.to_record(),
                    "fulfillment_type": _fulfillment(retailer_id, result),
                }
                key = (retailer_id, offer.retailer_product_id)
                # PDP enrichment is product-level, not observation-level. Retaining every
                # repeated store/keyword hit is wasteful and can exceed a small Railway
                # service's memory limit. The query order is deterministic and every
                # admitted row has a positive Search price, so the first observed context
                # is a valid, reproducible PDP request location for this product.
                observations_by_product.setdefault(key, observation)
                existing = admitted_products.get(key)
                candidate_record = {
                    "retailer_id": retailer_id,
                    "retailer_product_id": offer.retailer_product_id,
                    "title": offer.title,
                    "brand": offer.brand or "",
                    "price": str(offer.price) if offer.price is not None else "",
                    "zipcode": offer.zipcode or "",
                    "store_number": offer.store_number or "",
                    "url": offer.product_url or "",
                    "image_url": offer.image_url or "",
                    "raw_search_seller": observed_seller or "",
                }
                if existing is None or candidate_record["title"] < existing["title"]:
                    admitted_products[key] = candidate_record

        observations = list(observations_by_product.values())
        candidates = plan_product_detail_candidates(
            observations,
            analysis_offer_ids={str(observation["offer_id"]) for observation in observations},
        )
        pdp_catalog = ProductDetailCatalog.from_path(root)
        valid_candidates: list[tuple[Any, Any]] = []
        invalid_candidates: list[dict[str, str]] = []
        for candidate in candidates:
            try:
                endpoint = pdp_catalog.get(candidate.retailer_id)
                MetricsCartProductDetailAdapter(endpoint).build_request(candidate.context)
            except ValueError as exc:
                invalid_candidates.append(
                    {
                        "retailer_id": candidate.retailer_id,
                        "retailer_product_id": candidate.retailer_product_id,
                        "reason": str(exc),
                    }
                )
                continue
            valid_candidates.append((candidate, endpoint))

        checksums = [
            candidate.context.checksum(endpoint) for candidate, endpoint in valid_candidates
        ]
        fresh_cache: dict[str, dict[str, Any]] = {}
        if checksums:
            async with database.engine.connect() as connection:
                cached_rows = (
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT DISTINCT ON (s.request_checksum)
                                  s.request_checksum, p.retailer_id, p.retailer_product_id,
                                  p.identity, s.cache_expires_at,
                                  COALESCE(n.document->'normalized', s.document->'normalized')
                                    AS normalized
                                FROM canonical_product p
                                JOIN product_detail_snapshot s ON s.canonical_product_id = p.id
                                LEFT JOIN LATERAL (
                                  SELECT document
                                  FROM product_detail_normalization n
                                  WHERE n.product_detail_snapshot_id = s.id
                                    AND n.status = 'succeeded'
                                  ORDER BY n.completed_at DESC, n.id DESC LIMIT 1
                                ) n ON true
                                WHERE p.organization_id::text = :organization_id
                                  AND s.request_checksum = ANY(CAST(:checksums AS text[]))
                                  AND s.normalized AND s.http_status = 200
                                  AND s.cache_expires_at > now()
                                ORDER BY s.request_checksum, s.observed_at DESC, s.id DESC
                                """
                            ),
                            {"organization_id": ORGANIZATION_ID, "checksums": checksums},
                        )
                    )
                    .mappings()
                    .all()
                )
            fresh_cache = {str(row["request_checksum"]): dict(row) for row in cached_rows}

        cache_status_by_retailer: dict[str, Counter[str]] = defaultdict(Counter)
        credits_by_retailer: Counter[str] = Counter()
        pdp_plan_rows: list[dict[str, Any]] = []
        for candidate, endpoint in valid_candidates:
            checksum = candidate.context.checksum(endpoint)
            cached = fresh_cache.get(checksum)
            status = "fresh_cache" if cached is not None else "paid_call_required"
            cache_status_by_retailer[candidate.retailer_id][status] += 1
            if cached is None:
                credits_by_retailer[candidate.retailer_id] += endpoint.credits_per_successful_page
            normalized = cached.get("normalized") if cached else None
            identity = cached.get("identity") if cached else None
            seller = None
            if isinstance(normalized, dict):
                seller = normalized.get("seller")
            if seller is None and isinstance(identity, dict):
                seller = identity.get("seller")
            pdp_plan_rows.append(
                {
                    "retailer_id": candidate.retailer_id,
                    "retailer_product_id": candidate.retailer_product_id,
                    "observed_price": str(candidate.observed_price or ""),
                    "reason": candidate.reason,
                    "zipcode": candidate.context.zipcode or "",
                    "store": candidate.context.store or "",
                    "url": candidate.context.url or "",
                    "cache_status": status,
                    "fresh_cached_seller": str(seller or ""),
                    "credits_if_called": (
                        0 if cached is not None else endpoint.credits_per_successful_page
                    ),
                }
            )

        invalid_by_retailer: dict[str, Counter[str]] = defaultdict(Counter)
        for item in invalid_candidates:
            invalid_by_retailer[item["retailer_id"]][item["reason"]] += 1

        retailer_ids = sorted(
            set(task_status)
            | set(raw_result_count)
            | set(unique_scope_products)
            | set(cache_status_by_retailer)
            | set(invalid_by_retailer)
        )
        retailer_rows: list[dict[str, Any]] = []
        for retailer_id in retailer_ids:
            raw_count = raw_result_count[retailer_id]
            unique_raw = len(unique_raw_products[retailer_id])
            admitted = len(unique_scope_products[retailer_id])
            retailer_rows.append(
                {
                    "retailer_id": retailer_id,
                    "tasks_succeeded": task_status[retailer_id]["succeeded"],
                    "tasks_failed": task_status[retailer_id]["failed"],
                    "raw_search_rows": raw_count,
                    "normalized_rows": normalized_result_count[retailer_id],
                    "positive_price_rows": positive_price_count[retailer_id],
                    "sponsored_rows": sponsored_count[retailer_id],
                    "unique_raw_products": unique_raw,
                    "search_admitted_products": admitted,
                    "duplicate_keyword_hits_removed": max(raw_count - unique_raw, 0),
                    "fresh_pdp_requests": cache_status_by_retailer[retailer_id]["fresh_cache"],
                    "pdp_calls_required": cache_status_by_retailer[retailer_id][
                        "paid_call_required"
                    ],
                    "pdp_credits_required": credits_by_retailer[retailer_id],
                    "pdp_ineligible_requests": sum(invalid_by_retailer[retailer_id].values()),
                }
            )

        product_rows: list[dict[str, Any]] = []
        for key, product in sorted(admitted_products.items()):
            product_rows.append(
                {
                    **product,
                    "keyword_count": len(keywords_by_product[key]),
                    "keywords": " | ".join(
                        sorted(value for value in keywords_by_product[key] if value)
                    ),
                }
            )

        field_audit: dict[str, Any] = {}
        for retailer_id in retailer_ids:
            total = raw_result_count[retailer_id]
            field_audit[retailer_id] = {
                "raw_result_count": total,
                "raw_fields": dict(raw_field_counts[retailer_id].most_common()),
                "canonical_field_non_null": {
                    field: canonical_coverage[retailer_id][field] for field in CANONICAL_FIELDS
                },
                "canonical_field_coverage_pct": {
                    field: round(100 * canonical_coverage[retailer_id][field] / total, 2)
                    if total
                    else 0
                    for field in CANONICAL_FIELDS
                },
                "raw_search_sellers": dict(raw_seller_counts[retailer_id].most_common()),
                "scope_reasons": dict(scope_reasons[retailer_id].most_common()),
                "http_statuses": dict(http_status[retailer_id]),
            }

        _write_csv(output_dir / "retailer-summary.csv", retailer_rows)
        _write_csv(output_dir / "search-admitted-products.csv", product_rows)
        _write_csv(output_dir / "pdp-plan.csv", pdp_plan_rows)
        _write_csv(output_dir / "pdp-ineligible.csv", invalid_candidates)
        summary = {
            "schema_version": "1.0.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "run_ids": list(args.run_ids),
            "retailer_filter": sorted(set(args.retailer_ids or [])),
            "product_pack": {"id": pack.id, "version": pack.version, "checksum": pack.checksum},
            "checks": {
                "raw_artifact_checksum_failures": checksum_failures,
                "task_count": len(task_rows),
                "successful_tasks": sum(row["tasks_succeeded"] for row in retailer_rows),
                "failed_tasks": sum(row["tasks_failed"] for row in retailer_rows),
                "raw_search_rows": sum(row["raw_search_rows"] for row in retailer_rows),
                "unique_raw_products": sum(row["unique_raw_products"] for row in retailer_rows),
                "search_admitted_products": sum(
                    row["search_admitted_products"] for row in retailer_rows
                ),
                "fresh_pdp_requests": sum(row["fresh_pdp_requests"] for row in retailer_rows),
                "pdp_calls_required": sum(row["pdp_calls_required"] for row in retailer_rows),
                "pdp_credits_required": sum(row["pdp_credits_required"] for row in retailer_rows),
                "pdp_ineligible_requests": sum(
                    row["pdp_ineligible_requests"] for row in retailer_rows
                ),
            },
            "retailers": retailer_rows,
            "field_audit": field_audit,
            "pdp_ineligible_reasons": {
                retailer: dict(reasons) for retailer, reasons in invalid_by_retailer.items()
            },
            "governance": {
                "walmart_allowlist_products": len(
                    pack.document["retailer_overrides"]["walmart_us"]["products"]
                ),
                "search_availability_rule": "positive Search price",
                "seller_authority": "PDP seller; Search seller is diagnostic only",
                "pdp_cache_rule": "exact governed request context with unexpired 200 snapshot",
                "paid_calls_launched": False,
                "ai_calls_launched": False,
            },
        }
        required_credits = int(summary["checks"]["pdp_credits_required"])
        summary["pdp_budget"] = {
            "usd_per_credit": str(USD_PER_METRICSCART_CREDIT),
            "approved_spend_usd": (
                str(args.max_spend_usd) if args.max_spend_usd is not None else None
            ),
            "credit_ceiling": credit_ceiling,
            "required_credits": required_credits,
            "maximum_uncached_cost_usd": str(
                (Decimal(required_credits) * USD_PER_METRICSCART_CREDIT).quantize(Decimal("0.01"))
            ),
        }
        if args.confirm_paid_calls:
            if checksum_failures:
                raise ValueError("raw artifact checksum failures block paid PDP enrichment")
            if invalid_candidates:
                raise ValueError("PDP-ineligible admitted products block paid PDP enrichment")
            assert credit_ceiling is not None
            if required_credits > credit_ceiling:
                raise ValueError(
                    f"planned PDP cost {required_credits} credits exceeds "
                    f"the {credit_ceiling}-credit ceiling"
                )
            payable_checksums = [
                candidate.context.checksum(endpoint)
                for candidate, endpoint in valid_candidates
                if candidate.context.checksum(endpoint) not in fresh_cache
            ]
            active_jobs: list[dict[str, Any]] = []
            if payable_checksums:
                async with database.engine.connect() as connection:
                    active_jobs = [
                        dict(row)
                        for row in (
                            (
                                await connection.execute(
                                    text(
                                        """
                                        SELECT DISTINCT r.id::text AS run_id, r.status,
                                          count(*) OVER (PARTITION BY r.id) AS matching_jobs
                                        FROM product_detail_job j
                                        JOIN product_detail_enrichment_run r
                                          ON r.id = j.enrichment_run_id
                                        WHERE j.request_checksum = ANY(CAST(:checksums AS text[]))
                                          AND j.status IN ('queued', 'running')
                                          AND r.status IN ('planning', 'active')
                                        ORDER BY r.id::text
                                        """
                                    ),
                                    {"checksums": payable_checksums},
                                )
                            )
                            .mappings()
                            .all()
                        )
                    ]
            if active_jobs:
                summary["enrichment_run"] = {
                    "status": "existing_active_work",
                    "active_runs": active_jobs,
                    "jobs_created": 0,
                    "cache_hits": len(fresh_cache),
                }
            else:
                repository = PostgresProductDetailRepository(database.engine, root)
                run = await repository.create_run(max_credits=credit_ceiling)
                jobs_created = 0
                enqueue_cache_hits = 0
                for candidate, endpoint in valid_candidates:
                    observation = observations_by_product[
                        (candidate.retailer_id, candidate.retailer_product_id)
                    ]
                    product = await repository.upsert_serp_product(
                        retailer_id=candidate.retailer_id,
                        retailer_product_id=candidate.retailer_product_id,
                        name=str(observation.get("title") or candidate.retailer_product_id),
                        brand=(str(observation["brand"]) if observation.get("brand") else None),
                        url=str(candidate.context.url or ""),
                        image_primary=(
                            str(observation["image_url"]) if observation.get("image_url") else None
                        ),
                        identifiers={"product_id": candidate.retailer_product_id},
                        context={
                            "source": "live_search_collection",
                            "collection_run_ids": list(args.run_ids),
                            "product_pack_id": pack.id,
                            "product_pack_version": pack.version,
                            "source_offer_id": candidate.source_offer_id,
                            "zipcode": candidate.context.zipcode,
                            "store_number": candidate.context.store,
                            "fulfillment_type": candidate.context.fulfillment_type,
                            "observed_price": (
                                float(candidate.observed_price)
                                if candidate.observed_price is not None
                                else None
                            ),
                            "selection_reason": candidate.reason,
                        },
                    )
                    enqueue = await repository.enqueue(run.id, product, endpoint, candidate.context)
                    jobs_created += int(enqueue.created)
                    enqueue_cache_hits += int(enqueue.cached)
                summary["enrichment_run"] = {
                    "status": "queued" if jobs_created else "cache_satisfied",
                    "run_id": run.id,
                    "jobs_created": jobs_created,
                    "cache_hits": enqueue_cache_hits,
                    "credit_ceiling": credit_ceiling,
                }
                summary["governance"]["paid_calls_launched"] = jobs_created > 0
        (output_dir / "audit.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        return summary
    finally:
        await database.dispose()


def main() -> None:
    result = asyncio.run(_run(_arguments()))
    print(
        json.dumps(
            {
                "checks": result["checks"],
                "pdp_budget": result["pdp_budget"],
                "enrichment_run": result.get("enrichment_run"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
