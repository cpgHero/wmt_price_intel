"""Rebuild deterministic report presentation context from persisted historical evidence."""

from __future__ import annotations

import argparse
import asyncio
import bisect
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rci_analytics import (
    AssortmentAccumulator,
    CanonicalOfferNormalizer,
    CatalogProductPackLoader,
    ComparisonEngine,
    OfferClassifier,
    RelationshipInputReducer,
    benchmark_product_decisions,
    benchmark_product_evidence,
    benchmark_product_map_points,
    benchmark_product_match_candidates,
    complete_attributes_from_pdp,
    merge_assortment_product_context,
    merge_product_decision_context,
    merge_product_evidence_summary,
    primary_exact_profile,
    product_context_index,
    resolve_one_to_one_relationships,
)
from rci_analytics.models import ClassifiedOffer
from rci_analytics.normalization import RetailerIdentityMap
from rci_core import APP_VERSION, AppSettings
from rci_db import DatabaseProbe
from rci_product_packs import PostgresProductPackCatalog
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


class _BoundedQualityObservationSampler:
    """Retain stable leading sample candidates with bounded replay memory."""

    def __init__(self, max_rows: int) -> None:
        if max_rows < 1:
            raise ValueError("quality observation sample size must be positive")
        self._max_rows = max_rows
        self._buckets: dict[
            str,
            list[tuple[tuple[str, ...], tuple[str, ...], dict[str, object]]],
        ] = defaultdict(list)
        self._keys: dict[str, set[tuple[str, ...]]] = defaultdict(set)

    @staticmethod
    def _unique_key(row: dict[str, object]) -> tuple[str, ...]:
        return tuple(
            str(row.get(field) or "")
            for field in ("issue", "retailer", "product_id", "zipcode", "store", "reason")
        )

    @staticmethod
    def _sort_key(row: dict[str, object]) -> tuple[str, ...]:
        return tuple(
            str(row.get(field) or "")
            for field in ("retailer", "product", "zipcode", "store", "reason")
        )

    def add(self, row: dict[str, object]) -> None:
        issue = str(row["issue"])
        bucket = self._buckets[issue]
        retained_keys = self._keys[issue]
        unique_key = self._unique_key(row)
        if unique_key in retained_keys:
            return
        item = (self._sort_key(row), unique_key, row)
        if len(bucket) >= self._max_rows and item[:2] >= bucket[-1][:2]:
            return
        bisect.insort(bucket, item)
        retained_keys.add(unique_key)
        if len(bucket) > self._max_rows:
            retained_keys.remove(bucket.pop()[1])

    @property
    def retained_count(self) -> int:
        return sum(len(bucket) for bucket in self._buckets.values())

    def selected(self) -> list[dict[str, object]]:
        return _select_quality_observations(
            [item[2] for bucket in self._buckets.values() for item in bucket],
            max_rows=self._max_rows,
        )


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
        product_pack_catalog = PostgresProductPackCatalog(database.engine)
        pack = await CatalogProductPackLoader(
            repository_root,
            product_pack_catalog,
        ).load(record.product_pack_id, record.product_pack_version)
        benchmark = str(record.result["benchmark_retailer"])
        competitors = [str(value) for value in record.result.get("competitors", [])]
        configured_modes = {
            str(value.get("profile_id"))
            for value in record.result.get("comparison_modes", [])
            if isinstance(value, dict)
        }
        engine = ComparisonEngine(pack)
        profile = primary_exact_profile(pack, configured_profile_ids=configured_modes)
        review_profiles = [
            value
            for value in pack.matching_profiles
            if str(value.get("id")) in configured_modes
            and str(value.get("geography")) == "exact_zip"
        ]
        if not review_profiles:
            review_profiles = [profile]
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
        ).publication_highlights(
            source_artifact_ids,
            limit=1_000_000,
            per_retailer_limit=1_000_000,
        )
        pdp_context = product_context_index(highlights)
        reader = S3HistoricalCSVReader(bucket=bucket, client=client)
        normalizer = CanonicalOfferNormalizer(
            RetailerIdentityMap.from_catalog(repository_root / "config/retailer-catalog.json")
        )
        classifier = OfferClassifier(pack)
        relationship_reducer = RelationshipInputReducer(
            pack,
            profile_ids={str(value["id"]) for value in review_profiles},
        )
        assortment_accumulator = AssortmentAccumulator()
        quality_sampler = _BoundedQualityObservationSampler(args.max_quality_observations)
        for historical_source in sources:
            async for rows in reader.iter_batches(historical_source):
                for row in rows:
                    source_row = historical_source_row(row, historical_source)
                    try:
                        normalized = normalizer.normalize(source_row)
                    except ValueError as exc:
                        quality_sampler.add(
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
                        quality_sampler.add(
                            _offer_quality_observation(
                                classified,
                                issue="Missing or zero search price",
                                reason="Search result did not contain a positive USD price",
                            )
                        )
                    if classified.review_reasons:
                        quality_sampler.add(
                            _offer_quality_observation(
                                classified,
                                issue="Attribute review",
                                reason="; ".join(classified.review_reasons),
                            )
                        )
                    relationship_reducer.add(classified)
                    assortment_accumulator.add(classified)
        offers = relationship_reducer.offers()
        candidate_matches = [
            match
            for review_profile in review_profiles
            for competitor in competitors
            for match in engine.compare_products(
                offers,
                benchmark_id=benchmark,
                competitor_id=competitor,
                profile_id=str(review_profile["id"]),
            )
        ]
        decision_rules = pack.reporting["decision_rules"]
        profile_priority = [
            str(value)
            for value in decision_rules["profile_priority"]
            if any(str(review_profile["id"]) == str(value) for review_profile in review_profiles)
        ]
        resolution = resolve_one_to_one_relationships(
            offers,
            candidate_matches,
            benchmark_retailer=benchmark,
            profile_priority=profile_priority,
            profile_scope_policies={
                str(review_profile["id"]): dict(review_profile.get("relationship_scope_policy", {}))
                for review_profile in review_profiles
            },
        )
        review_matches = list(resolution.matches)
        matches = [match for match in review_matches if match.profile_id == str(profile["id"])]
        match_relationships = [dict(row) for row in resolution.relationships]
        ambiguous_match_groups = [dict(row) for row in resolution.ambiguous_groups]
        decision_rows = benchmark_product_decisions(
            offers,
            matches,
            benchmark_retailer=benchmark,
            decision_rules=decision_rules,
            qa_rules=pack.document["qa_rules"],
        )
        product_decisions = [row for row in decision_rows if row["qa_status"] == "ready"]
        suppressed_product_decisions = [row for row in decision_rows if row["qa_status"] != "ready"]
        map_points = benchmark_product_map_points(
            offers,
            matches,
            benchmark_retailer=benchmark,
            max_products=args.max_products,
            max_points_per_product=args.max_points_per_product,
            allowed_relationship_ids={
                str(row["relationship_id"])
                for row in product_decisions
                if row.get("relationship_id")
            },
        )
        match_candidates = benchmark_product_match_candidates(
            offers,
            candidate_matches,
            benchmark_retailer=benchmark,
            profiles=review_profiles,
            max_rows=2_000,
            max_locations_per_row=1,
        )
        relationship_index = {
            (
                str(row["competitor_id"]),
                str(row["benchmark_product_id"]),
                str(row["competitor_product_id"]),
            ): row
            for row in match_relationships
        }
        ambiguous_index = {
            (
                str(group["competitor_id"]),
                str(candidate["benchmark_product_id"]),
                str(candidate["competitor_product_id"]),
            ): str(group["candidate_group_id"])
            for group in ambiguous_match_groups
            for candidate in group["candidates"]
        }
        for candidate in match_candidates:
            key = (
                str(candidate["competitor"]),
                str(candidate["benchmark_product_id"]),
                str(candidate["competitor_product_id"]),
            )
            relationship = relationship_index.get(key)
            candidate["relationship_id"] = (
                str(relationship["relationship_id"]) if relationship is not None else None
            )
            candidate["relationship_status"] = (
                str(relationship["status"])
                if relationship is not None
                else "ambiguous"
                if key in ambiguous_index
                else "unmatched"
            )
            candidate["candidate_group_id"] = ambiguous_index.get(key)
            candidate["qa_status"] = (
                "review_required" if candidate["relationship_status"] == "ambiguous" else "ready"
            )
            candidate["suppression_reasons"] = (
                ["Automatic candidates do not have a unique one-to-one assignment"]
                if candidate["relationship_status"] == "ambiguous"
                else []
            )
        assortment_analysis = merge_assortment_product_context(
            assortment_accumulator.finalize(
                benchmark_retailer=benchmark,
                competitors=competitors,
                matches=review_matches,
                profiles=review_profiles,
                ambiguous_groups=ambiguous_match_groups,
            ),
            highlights,
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
        quality_observations = quality_sampler.selected()
        report_store = S3ReportObjectStore(bucket=bucket, client=client)
        service = AnalysisResultService(
            results_repository,
            AnalysisResultValidator(repository_root),
            report_store,
            ArtifactRenderer(repository_root),
            product_pack_catalog,
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
        context["suppressed_product_decisions"] = merge_product_decision_context(
            suppressed_product_decisions,
            highlights,
            benchmark_retailer=benchmark,
        )
        context["match_candidates"] = match_candidates
        context["match_relationships"] = match_relationships
        context["ambiguous_match_groups"] = ambiguous_match_groups
        context["assortment_analysis"] = assortment_analysis
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
