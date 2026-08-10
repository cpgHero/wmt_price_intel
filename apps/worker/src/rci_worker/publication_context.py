"""Rebuild deterministic report presentation context from persisted historical evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rci_analytics import (
    CanonicalOfferNormalizer,
    ComparisonEngine,
    ComparisonInputReducer,
    OfferClassifier,
    ProductPackLoader,
    benchmark_product_decisions,
    benchmark_product_evidence,
    benchmark_product_map_points,
    complete_attributes_from_pdp,
    merge_product_decision_context,
    merge_product_evidence_summary,
    product_context_index,
)
from rci_analytics.models import ClassifiedOffer
from rci_analytics.normalization import RetailerIdentityMap
from rci_core import APP_VERSION, AppSettings
from rci_db import DatabaseProbe
from rci_products import PostgresProductDetailRepository
from rci_results import (
    AnalysisResultService,
    AnalysisResultValidator,
    ArtifactRenderer,
    PostgresResultsRepository,
    S3ReportObjectStore,
)
from rci_worker.analysis import PostgresAnalysisQueue, S3HistoricalCSVReader, historical_source_row


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish benchmark-product map context from persisted analysis inputs. "
            "This command makes no MetricsCart or OpenAI calls."
        )
    )
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())),
    )
    parser.add_argument("--max-products", type=int, default=20)
    parser.add_argument("--max-points-per-product", type=int, default=150)
    parser.add_argument("--max-quality-observations", type=int, default=160)
    parser.add_argument("--expires-in-seconds", type=int, default=86_400)
    return parser.parse_args()


def _raw_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return value
    return None


def _raw_quality_observation(
    row: dict[str, Any],
    *,
    retailer_id: str,
    issue: str,
    reason: str,
) -> dict[str, object]:
    return {
        "issue": issue,
        "retailer": retailer_id,
        "product": _raw_value(row, "title", "name", "Product Name") or "Unavailable",
        "product_id": _raw_value(
            row,
            "retailer_product_id",
            "Retailer Product Id",
            "asin",
            "ASIN",
            "id",
        ),
        "price": _raw_value(row, "price", "Price"),
        "zipcode": _raw_value(
            row,
            "zipcode",
            "Zipcode",
            "pickup_zipcode",
            "shipping_delivery_zipcode",
            "Shipping Delivery Zipcode",
        ),
        "store": _raw_value(
            row,
            "store_number",
            "Retailer Store Id",
            "retailer_store_id",
            "pickup_store_id",
        ),
        "reason": reason,
        "source_url": _raw_value(row, "product_url", "url", "Url"),
        "image_url": _raw_value(row, "image_url", "image_primary", "Image Url"),
    }


def _offer_quality_observation(
    classified: ClassifiedOffer,
    *,
    issue: str,
    reason: str,
) -> dict[str, object]:
    offer = classified.offer
    return {
        "issue": issue,
        "retailer": offer.retailer_id,
        "product": offer.title,
        "product_id": offer.retailer_product_id,
        "price": float(offer.price) if offer.price is not None else None,
        "zipcode": offer.zipcode,
        "store": offer.store_number,
        "reason": reason,
        "source_url": offer.product_url,
        "image_url": offer.image_url,
    }


def _select_quality_observations(
    rows: list[dict[str, object]],
    *,
    max_rows: int,
) -> list[dict[str, object]]:
    """Return a stable, issue-balanced sample of source search observations."""

    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = tuple(
            str(row.get(field) or "")
            for field in ("issue", "retailer", "product_id", "zipcode", "store", "reason")
        )
        if key in seen:
            continue
        seen.add(key)
        buckets[str(row["issue"])].append(row)
    for values in buckets.values():
        values.sort(
            key=lambda row: tuple(
                str(row.get(field) or "")
                for field in ("retailer", "product", "zipcode", "store", "reason")
            )
        )
    ordered_issues = [
        issue
        for issue in (
            "Missing or zero search price",
            "Attribute review",
            "Normalization rejected",
        )
        if buckets.get(issue)
    ]
    if not ordered_issues:
        return []
    quota = max(1, max_rows // len(ordered_issues))
    selected = [row for issue in ordered_issues for row in buckets[issue][:quota]]
    if len(selected) < max_rows:
        remainder = [row for issue in ordered_issues for row in buckets[issue][quota:]]
        selected.extend(remainder[: max_rows - len(selected)])
    return selected[:max_rows]


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if (
        args.max_products < 1
        or args.max_points_per_product < 1
        or args.max_quality_observations < 1
    ):
        raise ValueError("presentation context limits must be positive")
    if not 60 <= args.expires_in_seconds <= 604_800:
        raise ValueError("expires-in-seconds must be between 60 and 604800")
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
        results_repository = PostgresResultsRepository(database.engine)
        record = await results_repository.get(args.analysis_id)
        if record is None:
            raise LookupError(f"analysis {args.analysis_id!r} was not found")
        source = record.result.get("source")
        if not isinstance(source, dict) or source.get("kind") != "historical_import":
            raise ValueError("presentation-context replay currently requires historical input")
        input_set_id = str(source["input_set_id"])
        pack = ProductPackLoader(repository_root).load(record.product_pack_id)
        benchmark = str(record.result["benchmark_retailer"])
        competitors = [str(value) for value in record.result.get("competitors", [])]
        configured_modes = {
            str(value.get("profile_id"))
            for value in record.result.get("comparison_modes", [])
            if isinstance(value, dict)
        }
        engine = ComparisonEngine(pack)
        exact_profiles = [
            profile
            for profile in pack.matching_profiles
            if str(profile["geography"]) == "exact_zip"
            and engine.comparison_metric(str(profile["id"])) == "package_price"
            and (not configured_modes or str(profile["id"]) in configured_modes)
        ]
        if not exact_profiles:
            exact_profiles = [
                profile
                for profile in pack.matching_profiles
                if str(profile["geography"]) == "exact_zip"
                and engine.comparison_metric(str(profile["id"])) == "package_price"
            ]
        if not exact_profiles:
            raise ValueError("Product Pack has no exact package-price comparison profile")
        profile = exact_profiles[0]
        queue = PostgresAnalysisQueue(
            database.engine,
            code_version=settings.app_version or APP_VERSION,
            historical_replay_enabled=True,
        )
        sources = await queue.historical_sources(input_set_id)
        if not sources:
            raise ValueError("historical analysis has no persisted source artifacts")
        source_artifact_ids = [str(value) for value in source.get("source_artifact_ids", [])]
        highlights = await PostgresProductDetailRepository(
            database.engine,
            repository_root,
        ).publication_highlights(source_artifact_ids, limit=64, per_retailer_limit=32)
        pdp_context = product_context_index(highlights)
        reader = S3HistoricalCSVReader(bucket=bucket, client=client)
        normalizer = CanonicalOfferNormalizer(
            RetailerIdentityMap.from_catalog(repository_root / "config/retailer-catalog.json")
        )
        classifier = OfferClassifier(pack)
        reducer = ComparisonInputReducer(pack, profile_ids={str(profile["id"])})
        quality_candidates: list[dict[str, object]] = []
        for historical_source in sources:
            async for rows in reader.iter_batches(historical_source):
                for row in rows:
                    source_row = historical_source_row(row, historical_source)
                    try:
                        normalized = normalizer.normalize(source_row)
                    except ValueError as exc:
                        quality_candidates.append(
                            _raw_quality_observation(
                                source_row,
                                retailer_id=str(
                                    _raw_value(source_row, "retailer_id", "Retailer")
                                    or historical_source.retailer_id
                                ),
                                issue="Normalization rejected",
                                reason=str(exc),
                            )
                        )
                        continue
                    classified = complete_attributes_from_pdp(
                        classifier.classify(normalized),
                        pdp_context.get(
                            f"{normalized.retailer_id}:{normalized.retailer_product_id}"
                        ),
                        classifier=classifier,
                        pack=pack,
                    )
                    if normalized.price is None or normalized.price <= 0:
                        quality_candidates.append(
                            _offer_quality_observation(
                                classified,
                                issue="Missing or zero search price",
                                reason="Search result did not contain a positive USD price",
                            )
                        )
                    if classified.review_reasons:
                        quality_candidates.append(
                            _offer_quality_observation(
                                classified,
                                issue="Attribute review",
                                reason="; ".join(classified.review_reasons),
                            )
                        )
                    reducer.add(classified)
        offers = reducer.offers()
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
        map_points = benchmark_product_map_points(
            offers,
            matches,
            benchmark_retailer=benchmark,
            max_products=args.max_products,
            max_points_per_product=args.max_points_per_product,
        )
        product_decisions = benchmark_product_decisions(
            offers,
            matches,
            benchmark_retailer=benchmark,
        )
        selected_product_keys = {
            (benchmark, str(row["benchmark_product_id"])) for row in product_decisions
        } | {
            (str(row["competitor"]), str(row["competitor_product_id"])) for row in product_decisions
        }
        evidence_offers = []
        for historical_source in sources:
            async for rows in reader.iter_batches(historical_source):
                for row in rows:
                    try:
                        normalized = normalizer.normalize(
                            historical_source_row(row, historical_source)
                        )
                    except ValueError:
                        continue
                    if (
                        normalized.retailer_id,
                        normalized.retailer_product_id,
                    ) in selected_product_keys:
                        classified = classifier.classify(normalized)
                        evidence_offers.append(
                            complete_attributes_from_pdp(
                                classified,
                                pdp_context.get(
                                    f"{normalized.retailer_id}:{normalized.retailer_product_id}"
                                ),
                                classifier=classifier,
                                pack=pack,
                            )
                        )
        product_evidence = benchmark_product_evidence(
            evidence_offers,
            product_decisions,
            benchmark_retailer=benchmark,
        )
        product_decisions = merge_product_evidence_summary(
            product_decisions,
            product_evidence,
        )
        quality_observations = _select_quality_observations(
            quality_candidates,
            max_rows=args.max_quality_observations,
        )
        report_store = S3ReportObjectStore(bucket=bucket, client=client)
        service = AnalysisResultService(
            results_repository,
            AnalysisResultValidator(repository_root),
            report_store,
            ArtifactRenderer(repository_root),
        )
        previous = await service.latest_publication(record.analysis_id)
        document = previous.result if previous is not None else record.result
        context = dict(previous.presentation_context) if previous is not None else {}
        context["map_points"] = map_points
        context["product_evidence"] = product_evidence
        context["quality_observations"] = quality_observations
        context["product_decisions"] = merge_product_decision_context(
            product_decisions,
            highlights,
            benchmark_retailer=benchmark,
        )
        if highlights:
            context["product_highlights"] = highlights
        publication = await service.publish_publication(
            record.analysis_id,
            document,
            presentation_context=context,
        )
        artifact = await service.generate_artifact(record.analysis_id, "html")
        download_url = await report_store.presign(
            artifact.storage_uri,
            expires_in_seconds=args.expires_in_seconds,
        )
        return {
            "status": "ready",
            "analysis_id": record.analysis_id,
            "publication_id": publication.id,
            "publication_version": publication.version,
            "map_points": len(map_points),
            "product_decisions": len(product_decisions),
            "product_evidence_rows": sum(
                len(value.get("rows", [])) for value in product_evidence.values()
            ),
            "quality_observations": len(quality_observations),
            "mapped_benchmark_products": len(
                {str(point["benchmark_product_id"]) for point in map_points}
            ),
            "outcomes": dict(Counter(str(point["outcome"]) for point in map_points)),
            "retailer_api_calls": 0,
            "model_calls": 0,
            "download_url": download_url,
        }
    finally:
        await database.dispose()


def main() -> None:
    print(json.dumps(asyncio.run(_run(_arguments())), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
