"""Plan or enqueue analysis-scoped Product Details enrichment with a hard credit ceiling."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from rci_analytics import (
    CanonicalOfferNormalizer,
    ComparisonEngine,
    ComparisonInputReducer,
    OfferClassifier,
    ProductPackLoader,
    benchmark_product_decisions,
    primary_exact_profile,
)
from rci_analytics.models import ClassifiedOffer
from rci_analytics.normalization import RetailerIdentityMap
from rci_core import APP_VERSION, AppSettings
from rci_db import DatabaseProbe
from rci_products import (
    MetricsCartProductDetailAdapter,
    PostgresProductDetailRepository,
    ProductDetailCatalog,
    plan_product_detail_candidates,
)
from rci_results import PostgresResultsRepository
from rci_worker.analysis import PostgresAnalysisQueue, S3HistoricalCSVReader, historical_source_row


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan decision-product PDP enrichment for a persisted analysis. The default "
            "is a read-only estimate; --confirm-paid-calls is required to enqueue work."
        )
    )
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())),
    )
    parser.add_argument("--max-product-pairs", type=int, default=16)
    parser.add_argument("--max-credits", type=int, default=1000)
    parser.add_argument(
        "--retailer",
        action="append",
        dest="retailers",
        default=[],
        help=(
            "Restrict the plan to one retailer ID. Repeat the option for multiple "
            "retailers; omit it to include all retailers."
        ),
    )
    parser.add_argument("--confirm-paid-calls", action="store_true")
    return parser.parse_args()


def _fulfillment(item: ClassifiedOffer) -> str | None:
    for field in ("fulfillment_type", "Fulfillment Type", "shipping_type"):
        value = item.offer.raw.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    if item.offer.retailer_id in {"walmart_us", "aldi_us"}:
        return "pickup"
    return None


def _observation(item: ClassifiedOffer) -> dict[str, Any]:
    return {**item.offer.to_record(), "fulfillment_type": _fulfillment(item)}


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.max_product_pairs < 1 or args.max_credits < 1:
        raise ValueError("Product pair and credit limits must be positive")
    settings = AppSettings.from_env()
    database = DatabaseProbe(settings.database_url)
    repository_root = args.repository_root.resolve(strict=True)
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        force_path_style = _enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True)
        client = boto3.client(
            "s3",
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT") or None,
            region_name=os.getenv("OBJECT_STORAGE_REGION") or None,
            aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY") or None,
            config=Config(s3={"addressing_style": "path" if force_path_style else "virtual"}),
        )
        bucket = os.environ["OBJECT_STORAGE_BUCKET"]
        results = PostgresResultsRepository(database.engine)
        record = await results.get(args.analysis_id)
        if record is None:
            raise LookupError(f"analysis {args.analysis_id!r} was not found")
        source = record.result.get("source")
        if not isinstance(source, dict) or source.get("kind") != "historical_import":
            raise ValueError("PDP replay currently requires a persisted historical analysis")
        pack = ProductPackLoader(repository_root).load(record.product_pack_id)
        benchmark = str(record.result["benchmark_retailer"])
        competitors = [str(value) for value in record.result.get("competitors", [])]
        configured_modes = {
            str(value.get("profile_id"))
            for value in record.result.get("comparison_modes", [])
            if isinstance(value, dict)
        }
        engine = ComparisonEngine(pack)
        profile = primary_exact_profile(pack, configured_profile_ids=configured_modes)
        queue = PostgresAnalysisQueue(
            database.engine,
            code_version=settings.app_version or APP_VERSION,
            historical_replay_enabled=True,
        )
        sources = await queue.historical_sources(str(source["input_set_id"]))
        source_artifact_by_offer_id: dict[str, str] = {}
        reader = S3HistoricalCSVReader(bucket=bucket, client=client)
        normalizer = CanonicalOfferNormalizer(
            RetailerIdentityMap.from_catalog(repository_root / "config/retailer-catalog.json")
        )
        classifier = OfferClassifier(pack)
        reducer = ComparisonInputReducer(pack, profile_ids={str(profile["id"])})
        for historical_source in sources:
            async for rows in reader.iter_batches(historical_source):
                for row in rows:
                    try:
                        normalized = normalizer.normalize(
                            historical_source_row(row, historical_source)
                        )
                    except ValueError:
                        continue
                    source_artifact_by_offer_id[normalized.offer_id] = (
                        historical_source.dataset_artifact_id
                    )
                    reducer.add(classifier.classify(normalized))
        offers = reducer.offers()
        offer_index = {item.offer.offer_id: item for item in offers}
        matches = [
            match
            for competitor in competitors
            for match in engine.compare(
                offers,
                benchmark_id=benchmark,
                competitor_id=competitor,
                profile_id=str(profile["id"]),
            )
        ]
        decisions = benchmark_product_decisions(
            offers,
            matches,
            benchmark_retailer=benchmark,
            max_rows=args.max_product_pairs,
        )
        selected_pairs = {
            (
                str(row["benchmark_product_id"]),
                str(row["competitor"]),
                str(row["competitor_product_id"]),
            )
            for row in decisions
        }
        analysis_offer_ids = {
            offer_id
            for match in matches
            if (
                offer_index[match.benchmark_offer_id].offer.retailer_product_id,
                match.competitor_id,
                offer_index[match.competitor_offer_id].offer.retailer_product_id,
            )
            in selected_pairs
            for offer_id in (match.benchmark_offer_id, match.competitor_offer_id)
        }
        candidates = plan_product_detail_candidates(
            (_observation(item) for item in offers),
            analysis_offer_ids=analysis_offer_ids,
        )
        retailer_filter = {str(value).strip() for value in args.retailers if str(value).strip()}
        catalog = ProductDetailCatalog.from_path(repository_root)
        valid_candidates = []
        invalid_candidates: list[dict[str, str]] = []
        for candidate in candidates:
            if retailer_filter and candidate.retailer_id not in retailer_filter:
                continue
            try:
                endpoint = catalog.get(candidate.retailer_id)
                MetricsCartProductDetailAdapter(endpoint).build_request(candidate.context)
            except ValueError as exc:
                invalid_candidates.append(
                    {
                        "retailer": candidate.retailer_id,
                        "product_id": candidate.retailer_product_id,
                        "reason": str(exc),
                    }
                )
                continue
            valid_candidates.append((candidate, endpoint))
        required_credits = sum(
            endpoint.credits_per_successful_page for _candidate, endpoint in valid_candidates
        )
        summary: dict[str, object] = {
            "status": "estimate" if not args.confirm_paid_calls else "queued",
            "analysis_id": record.analysis_id,
            "decision_product_pairs": len(decisions),
            "admitted_offer_observations": len(analysis_offer_ids),
            "unique_retailer_products": len(
                {
                    (candidate.retailer_id, candidate.retailer_product_id)
                    for candidate, _ in valid_candidates
                }
            ),
            "planned_calls": len(valid_candidates),
            "required_credits": required_credits,
            "credit_ceiling": args.max_credits,
            "retailer_filter": sorted(retailer_filter),
            "credits_by_retailer": dict(
                Counter(
                    {
                        retailer: sum(
                            endpoint.credits_per_successful_page
                            for candidate, endpoint in valid_candidates
                            if candidate.retailer_id == retailer
                        )
                        for retailer in {candidate.retailer_id for candidate, _ in valid_candidates}
                    }
                )
            ),
            "candidate_reasons": dict(
                Counter(candidate.reason for candidate, _ in valid_candidates)
            ),
            "invalid_candidates": invalid_candidates,
            "paid_calls_enqueued": 0,
        }
        if not args.confirm_paid_calls:
            return summary
        if required_credits > args.max_credits:
            raise ValueError(
                f"planned PDP cost {required_credits} credits exceeds {args.max_credits} ceiling"
            )
        repository = PostgresProductDetailRepository(database.engine, repository_root)
        run = await repository.create_run(max_credits=args.max_credits)
        queued = 0
        cached = 0
        for candidate, endpoint in valid_candidates:
            item = offer_index[candidate.source_offer_id]
            product = await repository.upsert_serp_product(
                retailer_id=candidate.retailer_id,
                retailer_product_id=candidate.retailer_product_id,
                name=item.offer.title,
                brand=item.offer.brand,
                url=item.offer.product_url or "",
                image_primary=item.offer.image_url,
                identifiers={"product_id": candidate.retailer_product_id},
                context={
                    "source": "analysis_admitted_match",
                    "analysis_id": record.analysis_id,
                    "source_artifact_id": source_artifact_by_offer_id.get(
                        candidate.source_offer_id
                    ),
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
            queued += int(enqueue.created)
            cached += int(enqueue.cached)
        summary.update(
            {
                "run_id": run.id,
                "paid_calls_enqueued": queued,
                "cache_hits": cached,
                "status": "queued" if queued else "cache_satisfied",
            }
        )
        return summary
    finally:
        await database.dispose()


def main() -> None:
    print(json.dumps(asyncio.run(_run(_arguments())), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
