"""Governed benchmark-product, benchmark-store price-leadership API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_analytics import (
    CatalogProductPackLoader,
    CompetitiveProductLeadershipProjector,
    ProductLeadershipRelationship,
    certify_competitive_product_leadership,
)
from rci_api.analyses import get_analysis_service
from rci_api.competitive_release_audit import (
    audit_competitive_portfolio_set,
    require_competitive_portfolio_set,
)
from rci_api.price_monitoring import PriceMonitoringService, get_price_monitoring_service
from rci_contracts import validate_instance
from rci_product_packs import PostgresProductPackCatalog
from rci_results import AnalysisResultService
from rci_results.service import AnalysisNotFoundError

router = APIRouter(prefix="/api/v1", tags=["competitive-product-leadership"])


def _unit(comparison_metric: str) -> str:
    if comparison_metric == "package_price":
        return "USD/package"
    return f"USD/{comparison_metric.removeprefix('price_per_').replace('_', ' ')}"


def _active_candidate_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        dict(row)
        for row in report.get("match_candidates", [])
        if isinstance(row, dict)
        and str(row.get("relationship_status")) in {"suggested", "confirmed"}
        and str(row.get("qa_status") or "ready") == "ready"
    ]
    if candidates:
        return candidates
    return [
        dict(row)
        for row in report.get("product_decisions", [])
        if isinstance(row, dict) and str(row.get("qa_status") or "ready") == "ready"
    ]


def _portfolio_summary(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status") or "unscored") for row in outcomes)
    scored = [row for row in outcomes if row.get("status") != "unscored"]
    gaps = [
        float(row["competitor_minus_benchmark"])
        for row in scored
        if row.get("competitor_minus_benchmark") is not None
    ]
    benchmark_lower = statuses["leader"] + statuses["at_risk"]
    competitor_lower = statuses["losing"]
    parity = statuses["tied"]
    return {
        "benchmark_product_locations": len(outcomes),
        "scored_product_locations": len(scored),
        "coverage_rate": round(len(scored) / len(outcomes), 4) if outcomes else None,
        "leader_product_locations": statuses["leader"],
        "tied_product_locations": statuses["tied"],
        "at_risk_product_locations": statuses["at_risk"],
        "losing_product_locations": statuses["losing"],
        "unscored_product_locations": statuses["unscored"],
        "leader_rate": (round(statuses["leader"] / len(scored), 4) if scored else None),
        "benchmark_lower_rate": (round(benchmark_lower / len(scored), 4) if scored else None),
        "competitor_lower_rate": (round(competitor_lower / len(scored), 4) if scored else None),
        "parity_rate": round(parity / len(scored), 4) if scored else None,
        "average_gap": round(sum(gaps) / len(gaps), 4) if gaps else None,
    }


def _normalized_attribute(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _attribute_key(value: Any) -> str:
    """Normalize Product Pack display labels to canonical attribute keys."""

    return "_".join(
        token
        for token in "".join(
            character.casefold() if character.isalnum() else " " for character in str(value or "")
        ).split()
        if token
    )


def _candidate_segment_rows(
    report: dict[str, Any],
    candidates: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Retain certified cohorts even when exact-location price overlap is absent."""

    dimensions = {
        _attribute_key(value)
        for value in report.get("product_pack", {}).get("cohort_dimensions", [])
        if _attribute_key(value)
    }

    def attributes(row: dict[str, Any], field: str) -> dict[str, Any]:
        source = row.get(field)
        if not isinstance(source, dict):
            return {}
        return {
            _attribute_key(name): value
            for name, value in source.items()
            if value is not None
            and (not dimensions or _attribute_key(name) in dimensions)
            and str(value).strip()
        }

    def signature(values: dict[str, Any]) -> str:
        normalized = {name: _normalized_attribute(value) for name, value in values.items()}
        return json.dumps(normalized, sort_keys=True, default=str)

    rows = []
    for row in existing:
        values = attributes(row, "_segment_attributes")
        if not values:
            continue
        rows.append(
            {
                **row,
                "_segment_attributes": values,
                "_segment_dimensions": sorted(dimensions),
            }
        )
    signatures = {
        (
            str(row.get("_competitor_id")),
            str(row.get("_profile_id")),
            signature(attributes(row, "_segment_attributes")),
        )
        for row in rows
    }
    for candidate in candidates:
        values = attributes(candidate, "match_attributes")
        if not values:
            continue
        competitor_id = str(candidate.get("competitor") or "")
        profile_id = str(candidate.get("profile_id") or "")
        serialized = signature(values)
        segment_signature = (competitor_id, profile_id, serialized)
        if not competitor_id or not profile_id or segment_signature in signatures:
            continue
        segment_id = f"segment-{hashlib.sha256(serialized.encode()).hexdigest()[:16]}"
        rows.append(
            {
                "_competitor_id": competitor_id,
                "_profile_id": profile_id,
                "_segment_id": segment_id,
                "_segment_attributes": values,
                "_segment_dimensions": sorted(dimensions),
                "competitor": competitor_id,
                "segment": " / ".join(
                    f"{name.replace('_', ' ').title()}: {value}" for name, value in values.items()
                ),
            }
        )
        signatures.add(segment_signature)
    return rows


def _attributes_match(
    candidate: dict[str, Any],
    segment: dict[str, Any],
    dimensions: set[str],
) -> bool:
    def projected(values: dict[str, Any]) -> dict[str, Any]:
        return {
            key: _normalized_attribute(value)
            for name, value in values.items()
            if (key := _attribute_key(name))
            and (not dimensions or key in dimensions)
            and value is not None
            and str(value).strip()
        }

    # Cohorts are a partition, not overlapping filters. A relationship whose
    # certified evidence contains Organic=True must not also enter the cohort
    # where organic evidence is absent merely because the other attributes
    # agree.
    return projected(candidate) == projected(segment)


def _compact_assortment_products(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [
        {
            "canonical_product_id": str(
                row.get("canonical_product_id")
                or f"{row.get('retailer_id', 'retailer')}:{row.get('product_id', '')}"
            ),
            "product_id": str(row.get("product_id") or ""),
            "name": str(row.get("name") or row.get("product_id") or "Unknown product"),
            "brand": row.get("brand"),
            "brand_type": str(row.get("brand_type") or "unclassified"),
            "image_url": row.get("image_url"),
            "observed_locations": int(row.get("observed_locations") or 0),
            "observed_zipcodes": int(row.get("observed_zipcodes") or 0),
        }
        for row in rows
        if isinstance(row, dict) and row.get("product_id")
    ]


def _retailer_token(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _assortment_products(assortment: Any, retailer_id: str) -> list[dict[str, Any]]:
    if not isinstance(assortment, dict):
        return []
    target = _retailer_token(retailer_id)
    for retailer in assortment.get("retailers", []):
        if not isinstance(retailer, dict) or _retailer_token(retailer.get("retailer")) != target:
            continue
        products = [dict(row) for row in retailer.get("products", []) if isinstance(row, dict)]
        return sorted(
            products,
            key=lambda row: (
                -int(row.get("observed_locations") or 0),
                str(row.get("name") or row.get("product_id") or "").casefold(),
            ),
        )
    return []


def _relationship_key(row: dict[str, Any]) -> str:
    return str(
        row.get("relationship_id")
        or row.get("id")
        or "|".join(
            (
                str(row.get("competitor") or ""),
                str(row.get("benchmark_product_id") or ""),
                str(row.get("competitor_product_id") or ""),
            )
        )
    )


def _coverage_rows(
    *,
    catalog: dict[str, dict[str, Any]],
    observed_products: dict[str, dict[str, Any]],
    identity_candidates: list[dict[str, Any]],
    selected_candidates: list[dict[str, Any]],
    product_summaries: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a mutually-exclusive denominator ledger for one competitor.

    Identity certification, price-basis eligibility, and local scoring are
    deliberately separate stages. This prevents a zero local score from being
    misread as a missing match and makes the complete benchmark catalog the
    authoritative denominator when the Product Pack supplies one.
    """

    identity_by_product: dict[str, set[str]] = {}
    selected_by_product: dict[str, set[str]] = {}
    selected_competitors_by_product: dict[str, set[str]] = {}
    candidate_names: dict[str, str] = {}
    candidate_images: dict[str, Any] = {}
    for row in identity_candidates:
        product_id = str(row.get("benchmark_product_id") or "")
        if not product_id:
            continue
        identity_by_product.setdefault(product_id, set()).add(_relationship_key(row))
        if row.get("benchmark_product_name"):
            candidate_names.setdefault(product_id, str(row["benchmark_product_name"]))
        if row.get("benchmark_image_url"):
            candidate_images.setdefault(product_id, row["benchmark_image_url"])
    for row in selected_candidates:
        product_id = str(row.get("benchmark_product_id") or "")
        if not product_id:
            continue
        selected_by_product.setdefault(product_id, set()).add(_relationship_key(row))
        competitor_product_id = str(row.get("competitor_product_id") or "")
        if competitor_product_id:
            selected_competitors_by_product.setdefault(product_id, set()).add(competitor_product_id)

    scored_by_product = {
        str(row.get("product_id")): int(row.get("scored_product_locations") or 0)
        for row in product_summaries
        if row.get("product_id")
    }
    product_ids = sorted(catalog)
    in_scope_product_ids = {
        product_id
        for product_id, product in catalog.items()
        if str(product.get("scope") or "include") != "exclude"
    }
    observed_product_ids = {
        product_id
        for product_id in in_scope_product_ids
        if int(observed_products.get(product_id, {}).get("observed_locations") or 0) > 0
    }
    certified_product_ids = observed_product_ids & set(identity_by_product)
    selected_product_ids = certified_product_ids & set(selected_by_product)
    locally_scored_product_ids = {
        product_id
        for product_id in selected_product_ids
        if scored_by_product.get(product_id, 0) > 0
    }
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    for product_id in product_ids:
        observed = observed_products.get(product_id, {})
        observed_locations = int(observed.get("observed_locations") or 0)
        certified_relationships = len(identity_by_product.get(product_id, set()))
        selected_relationships = len(selected_by_product.get(product_id, set()))
        scored_locations = scored_by_product.get(product_id, 0)
        if product_id not in in_scope_product_ids:
            status = "governed_out_of_scope"
        elif observed_locations == 0:
            status = "benchmark_not_observed"
        elif certified_relationships == 0:
            status = "no_certified_relationship"
        elif selected_relationships == 0:
            status = "no_selected_price_basis"
        elif scored_locations == 0:
            status = "no_local_competitor_evidence"
        else:
            status = "scored"
        status_counts[status] += 1
        catalog_row = catalog.get(product_id, {})
        rows.append(
            {
                "product_id": product_id,
                "product_name": str(
                    observed.get("name")
                    or candidate_names.get(product_id)
                    or catalog_row.get("name")
                    or f"Catalog product {product_id}"
                ),
                "image_url": observed.get("image_url")
                or candidate_images.get(product_id)
                or catalog_row.get("image_url"),
                "observed_locations": observed_locations,
                "status": status,
                "certified_relationships": certified_relationships,
                "selected_price_basis_relationships": selected_relationships,
                "selected_competitor_products": len(
                    selected_competitors_by_product.get(product_id, set())
                ),
                "scored_product_locations": scored_locations,
            }
        )
    status_order = {
        "scored": 0,
        "no_local_competitor_evidence": 1,
        "no_selected_price_basis": 2,
        "no_certified_relationship": 3,
        "benchmark_not_observed": 4,
        "governed_out_of_scope": 5,
    }
    rows.sort(
        key=lambda row: (
            status_order[str(row["status"])],
            -int(row["observed_locations"]),
            str(row["product_name"]).casefold(),
        )
    )
    funnel = {
        "catalog_products": len(product_ids),
        "in_scope_catalog_products": len(in_scope_product_ids),
        "observed_catalog_products": len(observed_product_ids),
        "certified_identity_products": len(certified_product_ids),
        "selected_price_basis_products": len(selected_product_ids),
        "locally_scored_products": len(locally_scored_product_ids),
        "scored_product_locations": sum(
            scored_by_product.get(product_id, 0) for product_id in locally_scored_product_ids
        ),
        "status_counts": {
            key: int(status_counts[key])
            for key in (
                "benchmark_not_observed",
                "no_certified_relationship",
                "no_selected_price_basis",
                "no_local_competitor_evidence",
                "scored",
                "governed_out_of_scope",
            )
        },
    }
    return funnel, rows


def _cohort_summary(
    *,
    segment_row: dict[str, Any],
    competitor_name: str,
    candidates: list[dict[str, Any]],
    product_views: dict[str, dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    attributes = dict(segment_row.get("_segment_attributes") or {})
    dimensions = {_attribute_key(value) for value in segment_row.get("_segment_dimensions", [])}
    included_candidates = [
        row
        for row in candidates
        if _attributes_match(
            dict(row.get("match_attributes") or {}),
            attributes,
            dimensions,
        )
    ]
    included_relationship_ids = {
        str(row.get("relationship_id") or row.get("id")) for row in included_candidates
    }
    benchmark_product_ids = sorted(
        {str(row["benchmark_product_id"]) for row in included_candidates}
    )
    outcomes = [
        dict(outcome)
        for product_id in benchmark_product_ids
        for outcome in product_views.get(product_id, {}).get("outcomes", [])
        if isinstance(outcome, dict)
        and str(outcome.get("relationship_id") or "") in included_relationship_ids
    ]
    scored = [row for row in outcomes if row.get("status") != "unscored"]
    benchmark_values = [
        float(row["benchmark"]["comparison_value"])
        for row in scored
        if isinstance(row.get("benchmark"), dict)
        and row["benchmark"].get("comparison_value") is not None
    ]
    competitor_values = [
        float(row["competitor"]["comparison_value"])
        for row in scored
        if isinstance(row.get("competitor"), dict)
        and row["competitor"].get("comparison_value") is not None
    ]
    gaps = [
        float(row["competitor_minus_benchmark"])
        for row in scored
        if row.get("competitor_minus_benchmark") is not None
    ]
    product_rows = []
    for product_id in benchmark_product_ids:
        view = product_views.get(product_id, {})
        product_outcomes = [
            dict(row)
            for row in view.get("outcomes", [])
            if isinstance(row, dict)
            and str(row.get("relationship_id") or "") in included_relationship_ids
        ]
        product_rows.append(
            {
                "product_id": product_id,
                "product_name": str(view.get("benchmark_product", {}).get("name") or product_id),
                "image_url": view.get("benchmark_product", {}).get("image_url"),
                "relationships": len(
                    {
                        str(row.get("relationship_id") or row.get("id"))
                        for row in included_candidates
                        if str(row.get("benchmark_product_id")) == product_id
                    }
                ),
                **_portfolio_summary(product_outcomes),
            }
        )
    product_rows.sort(
        key=lambda row: (
            -int(row["scored_product_locations"]),
            -int(row["benchmark_product_locations"]),
            str(row["product_name"]).casefold(),
        )
    )
    summary = _portfolio_summary(outcomes)
    if summary["competitor_lower_rate"] and summary["competitor_lower_rate"] > max(
        summary["benchmark_lower_rate"] or 0, summary["parity_rate"] or 0
    ):
        dominant_outcome = "competitor_lower"
    elif summary["benchmark_lower_rate"] and summary["benchmark_lower_rate"] > max(
        summary["competitor_lower_rate"] or 0, summary["parity_rate"] or 0
    ):
        dominant_outcome = "benchmark_lower"
    elif summary["parity_rate"]:
        dominant_outcome = "parity"
    else:
        dominant_outcome = "unavailable"
    return {
        "id": (
            f"{segment_row.get('_competitor_id')}:{segment_row.get('_profile_id')}:"
            f"{segment_row.get('_segment_id')}"
        ),
        "competitor_id": str(segment_row.get("_competitor_id")),
        # Segment rows are persisted analytical evidence and may retain a
        # canonical retailer id.  The portfolio read model owns presentation,
        # so keep every cohort aligned with the governed retailer display name.
        "competitor": competitor_name,
        "profile_id": str(segment_row.get("_profile_id")),
        "segment_id": str(segment_row.get("_segment_id")),
        "segment": str(segment_row.get("segment") or "Comparable cohort"),
        "attributes": attributes,
        "relationships": len(
            {str(row.get("relationship_id") or row.get("id")) for row in included_candidates}
        ),
        "benchmark_products": len(benchmark_product_ids),
        "competitor_products": len(
            {str(row["competitor_product_id"]) for row in included_candidates}
        ),
        **summary,
        "benchmark_median": round(median(benchmark_values), 4) if benchmark_values else None,
        "competitor_median": round(median(competitor_values), 4) if competitor_values else None,
        "paired_median_gap": round(median(gaps), 4) if gaps else None,
        "dominant_outcome": dominant_outcome,
        "products": product_rows,
        "product_relationships": [
            dict(row)
            for row in relationship_rows
            if str(row.get("relationship_id") or "") in included_relationship_ids
        ],
    }


class PostgresCompetitiveLeadershipRepository:
    """Persist publication-scoped radius read models without changing evidence."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def materialization(
        self, analysis_id: str, *, profile_id: str, radius_miles: int
    ) -> dict[str, Any] | None:
        statement = text(
            """
            SELECT materialization.document
            FROM competitive_portfolio_materialization materialization
            JOIN analysis_result result ON result.id = materialization.analysis_result_id
            WHERE result.analysis_id = :analysis_id
              AND materialization.profile_id = :profile_id
              AND materialization.radius_miles = :radius_miles
            """
        )
        async with self._engine.connect() as connection:
            document = await connection.scalar(
                statement,
                {
                    "analysis_id": analysis_id,
                    "profile_id": profile_id,
                    "radius_miles": radius_miles,
                },
            )
        return dict(document) if isinstance(document, dict) else None

    async def materializations(self, analysis_id: str) -> list[dict[str, Any]]:
        """Load the complete immutable basis-by-radius publication set."""

        statement = text(
            """
            SELECT materialization.document
            FROM competitive_portfolio_materialization materialization
            JOIN analysis_result result ON result.id = materialization.analysis_result_id
            WHERE result.analysis_id = :analysis_id
            ORDER BY materialization.profile_id, materialization.radius_miles
            """
        )
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement, {"analysis_id": analysis_id})).scalars()
            return [dict(row) for row in rows if isinstance(row, dict)]

    async def store_materialization(
        self,
        analysis_id: str,
        *,
        profile_id: str,
        radius_miles: int,
        document: dict[str, Any],
    ) -> None:
        await self.store_materializations(
            analysis_id,
            [
                {
                    **document,
                    "filters": {
                        **dict(document.get("filters") or {}),
                        "profile_id": profile_id,
                        "radius_miles": radius_miles,
                    },
                }
            ],
        )

    async def store_materializations(
        self,
        analysis_id: str,
        documents: list[dict[str, Any]],
    ) -> None:
        """Atomically replace a complete, already-certified portfolio set."""

        statement = text(
            """
            INSERT INTO competitive_portfolio_materialization (
              analysis_result_id, profile_id, radius_miles, source_revision, document
            )
            SELECT id, :profile_id, :radius_miles, checksum, CAST(:document AS jsonb)
            FROM analysis_result
            WHERE analysis_id = :analysis_id
            ON CONFLICT ON CONSTRAINT competitive_portfolio_materialization_scope_uq
            DO UPDATE SET source_revision = EXCLUDED.source_revision,
                          document = EXCLUDED.document,
                          materialized_at = now()
            RETURNING id
            """
        )
        async with self._engine.begin() as connection:
            for document in documents:
                filters = dict(document.get("filters") or {})
                result = await connection.scalar(
                    statement,
                    {
                        "analysis_id": analysis_id,
                        "profile_id": str(filters.get("profile_id") or ""),
                        "radius_miles": int(filters.get("radius_miles") or 0),
                        "document": json.dumps(
                            document,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                )
                if result is None:
                    raise LookupError(f"analysis {analysis_id!r} was not found")


class CompetitiveProductLeadershipService:
    def __init__(
        self,
        *,
        repository_root: Path,
        analyses: AnalysisResultService,
        price_monitoring: PriceMonitoringService,
        product_packs: CatalogProductPackLoader,
        repository: PostgresCompetitiveLeadershipRepository | None = None,
    ) -> None:
        self._root = repository_root
        self._analyses = analyses
        self._prices = price_monitoring
        self._packs = product_packs
        self._repository = repository
        self._projector = CompetitiveProductLeadershipProjector()
        self._cache: dict[tuple[str, ...], dict[str, Any]] = {}
        self._portfolio_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        # Analysis results and governed publications are immutable. Portfolio
        # materialization may project hundreds of benchmark-product groups, so
        # repeatedly loading and rendering the same multi-megabyte publication
        # is both wasteful and capable of exceeding the publication timeout.
        self._analysis_context_cache: dict[str, tuple[Any, dict[str, Any]]] = {}
        self._analysis_context_locks: dict[str, asyncio.Lock] = {}

    async def _analysis_context(self, analysis_id: str) -> tuple[Any, dict[str, Any]]:
        cached = self._analysis_context_cache.get(analysis_id)
        if cached is not None:
            return cached
        lock = self._analysis_context_locks.setdefault(analysis_id, asyncio.Lock())
        async with lock:
            cached = self._analysis_context_cache.get(analysis_id)
            if cached is not None:
                return cached
            analysis, report = await asyncio.gather(
                self._analyses.get(analysis_id),
                self._analyses.report_view(analysis_id),
            )
            context = (analysis, report)
            if len(self._analysis_context_cache) >= 16:
                self._analysis_context_cache.pop(next(iter(self._analysis_context_cache)))
            self._analysis_context_cache[analysis_id] = context
            return context

    async def _benchmark_catalog(
        self,
        analysis: Any,
        report: dict[str, Any],
        benchmark_retailer_id: str,
    ) -> dict[str, dict[str, Any]]:
        """Return the governed benchmark universe, falling back transparently.

        An allowlisted Product Pack catalog is authoritative. Categories that
        do not configure one retain the union of observed and certified
        benchmark products so the generic engine stays category-neutral.
        """

        if self._packs is not None:
            pack = await self._packs.load(
                str(analysis.product_pack_id),
                str(analysis.product_pack_version),
            )
            override = pack.document.get("retailer_overrides", {}).get(benchmark_retailer_id, {})
            products = override.get("products", {}) if isinstance(override, dict) else {}
            if isinstance(products, dict) and products:
                return {
                    str(product_id): {
                        "name": str(product.get("name") or "") if isinstance(product, dict) else "",
                        "image_url": (
                            product.get("image_url") if isinstance(product, dict) else None
                        ),
                        "scope": (
                            str(product.get("scope") or "include")
                            if isinstance(product, dict)
                            else "include"
                        ),
                    }
                    for product_id, product in products.items()
                }

        assortment = report.get("assortment_analysis")
        observed = _assortment_products(assortment, benchmark_retailer_id)
        catalog = {
            str(row["product_id"]): {
                "name": str(row.get("name") or row["product_id"]),
                "image_url": row.get("image_url"),
            }
            for row in observed
            if row.get("product_id")
        }
        for row in _active_candidate_rows(report):
            product_id = str(row.get("benchmark_product_id") or "")
            if product_id:
                catalog.setdefault(
                    product_id,
                    {
                        "name": str(row.get("benchmark_product_name") or product_id),
                        "image_url": row.get("benchmark_image_url"),
                    },
                )
        return catalog

    async def portfolio_view(
        self,
        analysis_id: str,
        *,
        competitor_id: str,
        profile_id: str | None,
        radius_miles: Literal[1, 3, 5],
        state: str | None,
        city: str | None,
        refresh: bool = False,
        publish: bool = True,
    ) -> dict[str, Any]:
        """Aggregate radius-native product-location outcomes by competitor.

        The existing immutable publication scorecards retain their historical
        exact-ZIP grain. This projection deliberately rebuilds the portfolio
        from the certified product relationships and the same store-radius
        engine used by the product workspaces; it never relabels legacy totals.
        """

        if city is not None and state is None:
            raise ValueError("a city filter requires its state")
        cache_key = (
            analysis_id,
            competitor_id,
            profile_id or "",
            str(radius_miles),
            state or "",
            city or "",
        )
        cached = self._portfolio_cache.get(cache_key)
        if cached is not None and not refresh:
            return cached

        analysis, report = await self._analysis_context(analysis_id)
        benchmark = dict(report["retailer_scope"]["benchmark"])
        configured_competitors = [dict(row) for row in report["retailer_scope"]["competitors"]]
        competitor_name_index = {str(row["id"]): str(row["name"]) for row in configured_competitors}
        if competitor_id != "all" and competitor_id not in competitor_name_index:
            raise ValueError(f"competitor {competitor_id!r} is not in this analysis")

        basis_index = {
            str(row["profile_id"]): dict(row)
            for row in report.get("comparison_bases", [])
            if isinstance(row, dict) and row.get("profile_id")
        }
        preferred_profile = next(
            (
                str(row["profile_id"])
                for row in report.get("comparison_bases", [])
                if row.get("scorecard_role") == "preferred"
                and str(row["profile_id"]) in basis_index
            ),
            sorted(basis_index)[0] if basis_index else "",
        )
        if profile_id and profile_id not in basis_index:
            raise LookupError("the selected comparison basis is not configured for this analysis")
        selected_profile = profile_id or preferred_profile
        if not selected_profile:
            raise LookupError("no decision-ready product relationship is available")

        if not refresh and self._repository is not None and state is None and city is None:
            stored = await self._repository.materialization(
                analysis_id,
                profile_id=selected_profile,
                radius_miles=radius_miles,
            )
            if stored is not None and stored.get("schema_version") == "1.4.0":
                if competitor_id != "all":
                    stored["filters"] = {
                        **dict(stored["filters"]),
                        "competitor_id": competitor_id,
                    }
                    stored["scorecards"] = [
                        row
                        for row in stored.get("scorecards", [])
                        if row.get("competitor_id") == competitor_id
                    ]
                    stored["cohorts"] = [
                        row
                        for row in stored.get("cohorts", [])
                        if row.get("competitor_id") == competitor_id
                    ]
                    stored["assortment_scorecards"] = [
                        row
                        for row in stored.get("assortment_scorecards", [])
                        if row.get("competitor_id") == competitor_id
                    ]
                validate_instance(
                    self._root,
                    "competitive-portfolio-scorecards.schema.json",
                    stored,
                    label=f"materialized-competitive-portfolio-scorecards:{analysis_id}",
                )
                self._portfolio_cache[cache_key] = stored
                return stored

        active_candidates = [
            row
            for row in _active_candidate_rows(report)
            if competitor_id == "all" or str(row.get("competitor")) == competitor_id
        ]
        candidates = [
            row for row in active_candidates if str(row.get("profile_id")) == selected_profile
        ]
        selected_basis = basis_index.get(selected_profile, {})
        observation_requests: dict[tuple[str, str], set[str]] = {}
        for row in candidates:
            comparison_metric = str(
                row.get("comparison_metric")
                or selected_basis.get("comparison_metric")
                or "package_price"
            )
            benchmark_product_id = str(row.get("benchmark_product_id") or "")
            competitor_product_id = str(row.get("competitor_product_id") or "")
            competitor_retailer_id = str(row.get("competitor") or "")
            if benchmark_product_id:
                observation_requests.setdefault(
                    (str(benchmark["id"]), comparison_metric), set()
                ).add(benchmark_product_id)
            if competitor_retailer_id and competitor_product_id:
                observation_requests.setdefault(
                    (competitor_retailer_id, comparison_metric), set()
                ).add(competitor_product_id)
        # Prime one immutable observation set per retailer/metric. Product-level
        # projections then read subsets from that superset instead of reopening
        # the same Parquet evidence once per benchmark product and radius.
        await asyncio.gather(
            *(
                self._prices.product_observations_for_products(
                    analysis_id,
                    retailer_id=retailer_id,
                    product_ids=sorted(product_ids),
                    comparison_metric=comparison_metric,
                )
                for (retailer_id, comparison_metric), product_ids in sorted(
                    observation_requests.items()
                )
            )
        )
        product_groups = sorted(
            {
                (str(row.get("competitor")), str(row.get("benchmark_product_id")))
                for row in candidates
                if row.get("competitor") and row.get("benchmark_product_id")
            }
        )
        semaphore = asyncio.Semaphore(8)

        async def project(group: tuple[str, str]) -> tuple[tuple[str, str], dict[str, Any] | None]:
            async with semaphore:
                try:
                    result = await self.view(
                        analysis_id,
                        competitor_id=group[0],
                        profile_id=selected_profile,
                        benchmark_product_id=group[1],
                        radius_miles=radius_miles,
                        state=state,
                        city=city,
                    )
                    return group, result
                except LookupError:
                    return group, None

        projected = await asyncio.gather(*(project(group) for group in product_groups))
        visible_competitors = [
            row
            for row in configured_competitors
            if competitor_id == "all" or str(row["id"]) == competitor_id
        ]
        grouped_candidates: dict[str, list[dict[str, Any]]] = {
            str(row["id"]): [] for row in visible_competitors
        }
        for row in candidates:
            grouped_candidates.setdefault(str(row.get("competitor")), []).append(row)
        projected_index = {group: result for group, result in projected}
        scorecards: list[dict[str, Any]] = []
        cohorts: list[dict[str, Any]] = []
        assortment_scorecards: list[dict[str, Any]] = []
        segment_rows = _candidate_segment_rows(
            report,
            candidates,
            [
                dict(row)
                for section in report.get("sections", [])
                if isinstance(section, dict) and section.get("kind") == "segment_analysis"
                for row in section.get("records", [])
                if isinstance(row, dict)
                and str(row.get("_profile_id")) == selected_profile
                and str(row.get("_segment_id")) != "all"
            ],
        )
        assortment = report.get("assortment_analysis")
        assortment_comparisons = (
            assortment.get("comparisons", []) if isinstance(assortment, dict) else []
        )
        benchmark_assortment_products = _assortment_products(assortment, str(benchmark["id"]))
        benchmark_observed_index = {
            str(row["product_id"]): row
            for row in benchmark_assortment_products
            if row.get("product_id")
        }
        benchmark_observed_ids = {
            str(row.get("product_id"))
            for row in benchmark_assortment_products
            if row.get("product_id")
        }
        benchmark_catalog = await self._benchmark_catalog(
            analysis,
            report,
            str(benchmark["id"]),
        )
        for competitor in visible_competitors:
            retailer_id = str(competitor["id"])
            retailer_candidates = grouped_candidates.get(retailer_id, [])
            retailer_identity_candidates = [
                row for row in active_candidates if str(row.get("competitor")) == retailer_id
            ]
            benchmark_product_ids = sorted(
                {
                    str(row.get("benchmark_product_id"))
                    for row in retailer_candidates
                    if row.get("benchmark_product_id")
                }
            )
            competitor_product_ids = {
                str(row.get("competitor_product_id"))
                for row in retailer_candidates
                if row.get("competitor_product_id")
            }
            relationship_ids = {
                str(
                    row.get("relationship_id")
                    or "|".join(
                        (
                            str(row.get("competitor")),
                            str(row.get("benchmark_product_id")),
                            str(row.get("competitor_product_id")),
                            str(row.get("profile_id")),
                        )
                    )
                )
                for row in retailer_candidates
            }
            outcomes: list[dict[str, Any]] = []
            products: list[dict[str, Any]] = []
            product_relationships: list[dict[str, Any]] = []
            product_views: dict[str, dict[str, Any]] = {}
            for benchmark_product_id in benchmark_product_ids:
                view = projected_index.get((retailer_id, benchmark_product_id))
                if view is None:
                    # Certification remains authoritative when Search has no
                    # positive benchmark observation for this product. Retain
                    # the identity rows with explicit zero scored evidence so
                    # scorecard counts, included-product drawers, and the
                    # release audit cannot silently lose the relationship.
                    fallback_candidates = [
                        row
                        for row in retailer_candidates
                        if str(row.get("benchmark_product_id")) == benchmark_product_id
                    ]
                    first = fallback_candidates[0]
                    products.append(
                        {
                            "product_id": benchmark_product_id,
                            "product_name": str(
                                first.get("benchmark_product_name") or benchmark_product_id
                            ),
                            "image_url": first.get("benchmark_image_url"),
                            "relationships": len(
                                {
                                    str(row.get("relationship_id") or row.get("id"))
                                    for row in fallback_candidates
                                }
                            ),
                            **_portfolio_summary([]),
                        }
                    )
                    for row in fallback_candidates:
                        product_relationships.append(
                            {
                                "relationship_id": str(row.get("relationship_id") or row.get("id")),
                                "competitor_id": retailer_id,
                                "competitor_name": competitor_name_index.get(
                                    retailer_id, retailer_id
                                ),
                                "benchmark_product_id": benchmark_product_id,
                                "benchmark_product_name": str(
                                    row.get("benchmark_product_name") or benchmark_product_id
                                ),
                                "benchmark_image_url": row.get("benchmark_image_url"),
                                "competitor_product_id": str(
                                    row.get("competitor_product_id") or "Unknown product"
                                ),
                                "competitor_product_name": str(
                                    row.get("competitor_product_name")
                                    or row.get("competitor_product_id")
                                    or "Unknown product"
                                ),
                                "competitor_brand": row.get("competitor_brand"),
                                "competitor_brand_type": str(
                                    row.get("competitor_brand_type") or "unclassified"
                                ),
                                "competitor_image_url": row.get("competitor_image_url"),
                                "profile_id": str(row.get("profile_id") or selected_profile),
                                "profile_label": str(row.get("profile_label") or selected_profile),
                                "comparison_metric": str(
                                    row.get("comparison_metric") or "package_price"
                                ),
                                "comparison_unit": str(
                                    basis_index.get(selected_profile, {}).get("price_unit")
                                    or _unit(str(row.get("comparison_metric") or "package_price"))
                                ),
                                "scope_mode": "observed_benchmark_product_footprint",
                                "scoped_benchmark_locations": 0,
                                **_portfolio_summary([]),
                            }
                        )
                    continue
                product_views[benchmark_product_id] = view
                product_outcomes = [
                    dict(row) for row in view.get("outcomes", []) if isinstance(row, dict)
                ]
                outcomes.extend(product_outcomes)
                product_summary = _portfolio_summary(product_outcomes)
                products.append(
                    {
                        "product_id": benchmark_product_id,
                        "product_name": str(
                            view.get("benchmark_product", {}).get("name") or benchmark_product_id
                        ),
                        "image_url": view.get("benchmark_product", {}).get("image_url"),
                        "relationships": len(view.get("relationships", [])),
                        **product_summary,
                    }
                )
                outcomes_by_relationship: dict[str, list[dict[str, Any]]] = {}
                for outcome in product_outcomes:
                    relationship_id = str(outcome.get("relationship_id") or "")
                    if relationship_id:
                        outcomes_by_relationship.setdefault(relationship_id, []).append(outcome)
                for relationship in view.get("relationships", []):
                    if not isinstance(relationship, dict) or not relationship.get(
                        "relationship_id"
                    ):
                        continue
                    relationship_id = str(relationship["relationship_id"])
                    product_relationships.append(
                        {
                            "relationship_id": relationship_id,
                            "competitor_id": str(relationship.get("competitor_id") or retailer_id),
                            "competitor_name": str(
                                relationship.get("competitor_name")
                                or competitor_name_index.get(retailer_id, retailer_id)
                            ),
                            "benchmark_product_id": str(
                                relationship.get("benchmark_product_id") or benchmark_product_id
                            ),
                            "benchmark_product_name": str(
                                relationship.get("benchmark_product_name")
                                or view.get("benchmark_product", {}).get("name")
                                or benchmark_product_id
                            ),
                            "benchmark_image_url": relationship.get("benchmark_image_url")
                            or view.get("benchmark_product", {}).get("image_url"),
                            "competitor_product_id": str(
                                relationship.get("competitor_product_id") or "Unknown product"
                            ),
                            "competitor_product_name": str(
                                relationship.get("competitor_product_name")
                                or relationship.get("competitor_product_id")
                                or "Unknown product"
                            ),
                            "competitor_brand": relationship.get("competitor_brand"),
                            "competitor_brand_type": str(
                                relationship.get("competitor_brand_type") or "unclassified"
                            ),
                            "competitor_image_url": relationship.get("competitor_image_url"),
                            "profile_id": str(relationship.get("profile_id") or selected_profile),
                            "profile_label": str(
                                relationship.get("profile_label") or selected_profile
                            ),
                            "comparison_metric": str(
                                relationship.get("comparison_metric") or "package_price"
                            ),
                            "comparison_unit": str(
                                relationship.get("comparison_unit") or "USD/package"
                            ),
                            "scope_mode": str(relationship.get("scope_mode") or "global"),
                            "scoped_benchmark_locations": int(
                                relationship.get("scoped_benchmark_locations") or 0
                            ),
                            **_portfolio_summary(outcomes_by_relationship.get(relationship_id, [])),
                        }
                    )
            products.sort(
                key=lambda row: (
                    -int(row["scored_product_locations"]),
                    -int(row["benchmark_product_locations"]),
                    str(row["product_name"]).casefold(),
                )
            )
            product_relationships.sort(
                key=lambda row: (
                    -int(row["scored_product_locations"]),
                    str(row["benchmark_product_name"]).casefold(),
                    str(row["competitor_product_name"]).casefold(),
                )
            )
            evidence_funnel, _coverage_products = _coverage_rows(
                catalog=benchmark_catalog,
                observed_products=benchmark_observed_index,
                identity_candidates=retailer_identity_candidates,
                selected_candidates=retailer_candidates,
                product_summaries=products,
            )
            scorecards.append(
                {
                    "competitor_id": retailer_id,
                    "competitor": competitor_name_index.get(retailer_id, retailer_id),
                    "benchmark_products": len(benchmark_product_ids),
                    "competitor_products": len(competitor_product_ids),
                    "relationships": len(relationship_ids),
                    "evidence_funnel": evidence_funnel,
                    **_portfolio_summary(outcomes),
                    "products": products,
                    "product_relationships": product_relationships,
                }
            )
            retailer_segments = [
                row for row in segment_rows if str(row.get("_competitor_id")) == retailer_id
            ]
            cohorts.extend(
                _cohort_summary(
                    segment_row=row,
                    competitor_name=competitor_name_index.get(retailer_id, retailer_id),
                    candidates=retailer_candidates,
                    product_views=product_views,
                    relationship_rows=product_relationships,
                )
                for row in retailer_segments
            )
            legacy_assortment = next(
                (
                    dict(row)
                    for row in assortment_comparisons
                    if isinstance(row, dict) and str(row.get("competitor")) == retailer_id
                ),
                {},
            )
            competitor_assortment_products = _assortment_products(assortment, retailer_id)
            competitor_observed_ids = {
                str(row.get("product_id"))
                for row in competitor_assortment_products
                if row.get("product_id")
            }
            has_observed_assortment = bool(
                benchmark_assortment_products or competitor_assortment_products
            )
            matched_observed_benchmark_ids = set(benchmark_product_ids) & benchmark_observed_ids
            matched_observed_competitor_ids = competitor_product_ids & competitor_observed_ids
            benchmark_only_ids = benchmark_observed_ids - matched_observed_benchmark_ids
            competitor_whitespace_ids = competitor_observed_ids - matched_observed_competitor_ids
            radius_summary = _portfolio_summary(outcomes)
            assortment_scorecards.append(
                {
                    "competitor_id": retailer_id,
                    "competitor": competitor_name_index.get(retailer_id, retailer_id),
                    "profile_id": selected_profile,
                    "relationships": len(relationship_ids),
                    "matched_benchmark_products": (
                        len(matched_observed_benchmark_ids)
                        if has_observed_assortment
                        else len(benchmark_product_ids)
                    ),
                    "matched_competitor_products": (
                        len(matched_observed_competitor_ids)
                        if has_observed_assortment
                        else len(competitor_product_ids)
                    ),
                    "benchmark_only_products": (
                        len(benchmark_only_ids)
                        if has_observed_assortment
                        else int(legacy_assortment.get("benchmark_only_products") or 0)
                    ),
                    "competitor_whitespace_products": (
                        len(competitor_whitespace_ids)
                        if has_observed_assortment
                        else int(legacy_assortment.get("competitor_whitespace_products") or 0)
                    ),
                    "benchmark_match_coverage": (
                        (
                            round(
                                len(matched_observed_benchmark_ids) / len(benchmark_observed_ids),
                                4,
                            )
                            if benchmark_observed_ids
                            else None
                        )
                        if has_observed_assortment
                        else legacy_assortment.get("benchmark_match_coverage")
                    ),
                    "competitor_match_coverage": (
                        (
                            round(
                                len(matched_observed_competitor_ids) / len(competitor_observed_ids),
                                4,
                            )
                            if competitor_observed_ids
                            else None
                        )
                        if has_observed_assortment
                        else legacy_assortment.get("competitor_match_coverage")
                    ),
                    "profiles": list(legacy_assortment.get("profiles") or []),
                    "top_benchmark_only": _compact_assortment_products(
                        [
                            row
                            for row in benchmark_assortment_products
                            if str(row.get("product_id")) in benchmark_only_ids
                        ][:12]
                        if has_observed_assortment
                        else legacy_assortment.get("top_benchmark_only")
                    ),
                    "top_competitor_whitespace": _compact_assortment_products(
                        [
                            row
                            for row in competitor_assortment_products
                            if str(row.get("product_id")) in competitor_whitespace_ids
                        ][:12]
                        if has_observed_assortment
                        else legacy_assortment.get("top_competitor_whitespace")
                    ),
                    "products": products,
                    **radius_summary,
                }
            )
        scorecards.sort(
            key=lambda row: (
                -int(row["scored_product_locations"]),
                str(row["competitor"]).casefold(),
            )
        )
        cohorts.sort(
            key=lambda row: (
                -int(row["scored_product_locations"]),
                str(row["competitor"]).casefold(),
                str(row["segment"]).casefold(),
            )
        )
        assortment_scorecards.sort(
            key=lambda row: (
                -int(row["scored_product_locations"]),
                str(row["competitor"]).casefold(),
            )
        )
        result = {
            "schema_version": "1.4.0",
            "analysis_id": analysis_id,
            "generated_at": str(report["generated_at"]),
            "benchmark_retailer": benchmark,
            "filters": {
                "competitor_id": competitor_id,
                "profile_id": selected_profile,
                "radius_miles": radius_miles,
                "state": state,
                "city": city,
            },
            "policy": {
                "physical_store_rule": "within selected radius",
                "service_area_rule": "same delivery ZIP",
                "grain": "certified product relationship x observed Walmart product-store",
            },
            "scorecards": scorecards,
            "cohorts": cohorts,
            "assortment_scorecards": assortment_scorecards,
        }
        validate_instance(
            self._root,
            "competitive-portfolio-scorecards.schema.json",
            result,
            label=f"competitive-portfolio-scorecards:{analysis_id}",
        )
        if (
            self._repository is not None
            and competitor_id == "all"
            and state is None
            and city is None
            and publish
        ):
            await self._repository.store_materialization(
                analysis_id,
                profile_id=selected_profile,
                radius_miles=radius_miles,
                document=result,
            )
        if publish:
            if len(self._portfolio_cache) >= 32:
                self._portfolio_cache.pop(next(iter(self._portfolio_cache)))
            self._portfolio_cache[cache_key] = result
        return result

    async def product_coverage_view(
        self,
        analysis_id: str,
        *,
        competitor_id: str,
        profile_id: str | None,
        radius_miles: Literal[1, 3, 5],
    ) -> dict[str, Any]:
        """Explain every benchmark catalog product's reporting disposition."""

        if competitor_id == "all":
            raise ValueError("product coverage requires one competitor")
        analysis, report = await self._analysis_context(analysis_id)
        portfolio = await self.portfolio_view(
            analysis_id,
            competitor_id=competitor_id,
            profile_id=profile_id,
            radius_miles=radius_miles,
            state=None,
            city=None,
        )
        scorecard = next(
            (
                dict(row)
                for row in portfolio.get("scorecards", [])
                if str(row.get("competitor_id")) == competitor_id
            ),
            None,
        )
        if scorecard is None:
            raise LookupError("the selected competitor has no reporting scorecard")
        benchmark = dict(portfolio["benchmark_retailer"])
        assortment = report.get("assortment_analysis")
        observed_products = {
            str(row["product_id"]): row
            for row in _assortment_products(assortment, str(benchmark["id"]))
            if row.get("product_id")
        }
        catalog = await self._benchmark_catalog(
            analysis,
            report,
            str(benchmark["id"]),
        )
        active = [
            row
            for row in _active_candidate_rows(report)
            if str(row.get("competitor")) == competitor_id
        ]
        selected_profile = str(portfolio["filters"]["profile_id"])
        selected = [row for row in active if str(row.get("profile_id")) == selected_profile]
        funnel, products = _coverage_rows(
            catalog=catalog,
            observed_products=observed_products,
            identity_candidates=active,
            selected_candidates=selected,
            product_summaries=[
                dict(row) for row in scorecard.get("products", []) if isinstance(row, dict)
            ],
        )
        result = {
            "schema_version": "1.0.0",
            "analysis_id": analysis_id,
            "benchmark_retailer": benchmark,
            "competitor": {
                "id": competitor_id,
                "name": str(scorecard["competitor"]),
            },
            "profile_id": selected_profile,
            "radius_miles": radius_miles,
            "evidence_funnel": funnel,
            "products": products,
        }
        validate_instance(
            self._root,
            "competitive-product-coverage.schema.json",
            result,
            label=f"competitive-product-coverage:{analysis_id}:{competitor_id}",
        )
        return result

    async def decision_quality_view(self, analysis_id: str) -> dict[str, Any]:
        """Return the publication's complete profile-by-radius-by-retailer audit."""

        if self._repository is None:
            raise LookupError("competitive decision quality requires stored materializations")
        _analysis, report = await self._analysis_context(analysis_id)
        profiles = sorted(
            {
                str(row["profile_id"])
                for row in report.get("comparison_bases", [])
                if isinstance(row, dict) and row.get("profile_id")
            }
        )
        documents = await self._repository.materializations(analysis_id)
        if not documents:
            raise LookupError("competitive decision quality has not been materialized")
        result = audit_competitive_portfolio_set(
            documents,
            expected_profiles=profiles,
        )
        validate_instance(
            self._root,
            "competitive-decision-quality.schema.json",
            result,
            label=f"competitive-decision-quality:{analysis_id}",
        )
        return result

    async def pre_materialize_portfolios(
        self, analysis_id: str, *, refresh: bool = False
    ) -> list[dict[str, Any]]:
        _analysis, report = await self._analysis_context(analysis_id)
        readiness = report.get("report_readiness")
        blocking_reasons = (
            readiness.get("blocking_reasons", []) if isinstance(readiness, dict) else []
        )
        if blocking_reasons:
            codes = sorted(
                {
                    str(row.get("code") or "report_not_ready")
                    for row in blocking_reasons
                    if isinstance(row, dict)
                }
            )
            raise ValueError(
                "competitive portfolio materialization requires a decision-ready report: "
                + ", ".join(codes)
            )
        profiles = sorted(
            {
                str(row["profile_id"])
                for row in report.get("comparison_bases", [])
                if isinstance(row, dict) and row.get("profile_id")
            }
        )
        documents: list[dict[str, Any]] = []
        # Each portfolio already performs bounded product-level concurrency. Build
        # profile/radius documents sequentially so publication cannot multiply
        # object-store and database pressure across every portfolio at once.
        for profile_id in profiles:
            for radius in cast(tuple[Literal[1, 3, 5], ...], (1, 3, 5)):
                documents.append(
                    await self.portfolio_view(
                        analysis_id,
                        competitor_id="all",
                        profile_id=profile_id,
                        radius_miles=radius,
                        state=None,
                        city=None,
                        refresh=refresh,
                        publish=False,
                    )
                )
        require_competitive_portfolio_set(
            documents,
            expected_profiles=profiles,
        )
        if self._repository is not None:
            await self._repository.store_materializations(analysis_id, documents)
        for key in [key for key in self._portfolio_cache if key[0] == analysis_id]:
            self._portfolio_cache.pop(key, None)
        return documents

    async def view(
        self,
        analysis_id: str,
        *,
        competitor_id: str,
        profile_id: str | None,
        benchmark_product_id: str | None,
        radius_miles: Literal[1, 3, 5],
        state: str | None,
        city: str | None,
    ) -> dict[str, Any]:
        if city is not None and state is None:
            raise ValueError("a city filter requires its state")
        cache_key = (
            analysis_id,
            competitor_id,
            profile_id or "",
            benchmark_product_id or "",
            str(radius_miles),
            state or "",
            city or "",
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        analysis, report = await self._analysis_context(analysis_id)
        benchmark = dict(report["retailer_scope"]["benchmark"])
        configured_competitors = [dict(row) for row in report["retailer_scope"]["competitors"]]
        competitor_name_index = {str(row["id"]): str(row["name"]) for row in configured_competitors}
        if competitor_id != "all" and competitor_id not in competitor_name_index:
            raise ValueError(f"competitor {competitor_id!r} is not in this analysis")

        candidates = _active_candidate_rows(report)
        if competitor_id != "all":
            candidates = [row for row in candidates if str(row.get("competitor")) == competitor_id]
        basis_index = {
            str(row["profile_id"]): dict(row)
            for row in report.get("comparison_bases", [])
            if isinstance(row, dict) and row.get("profile_id")
        }
        available_profiles = set(basis_index)
        preferred_profile = next(
            (
                str(row["profile_id"])
                for row in report.get("comparison_bases", [])
                if row.get("scorecard_role") == "preferred"
                and str(row["profile_id"]) in available_profiles
            ),
            sorted(available_profiles)[0] if available_profiles else "",
        )
        if profile_id and profile_id not in available_profiles:
            raise LookupError("the selected comparison basis is not configured for this analysis")
        selected_profile = profile_id or preferred_profile
        if not selected_profile:
            raise LookupError("no decision-ready product relationship is available")
        candidates = [row for row in candidates if str(row.get("profile_id")) == selected_profile]

        product_rows: dict[str, dict[str, Any]] = {}
        product_rank: dict[str, int] = {}
        assortment = report.get("assortment_analysis")
        assortment_retailers = (
            assortment.get("retailers", []) if isinstance(assortment, dict) else []
        )
        benchmark_assortment = next(
            (
                row
                for row in assortment_retailers
                if isinstance(row, dict) and str(row.get("retailer")) == str(benchmark["id"])
            ),
            {},
        )
        for row in benchmark_assortment.get("products", []):
            if not isinstance(row, dict):
                continue
            product_id = str(row.get("product_id") or "")
            if not product_id:
                continue
            product_rows[product_id] = {
                "id": product_id,
                "name": str(row.get("name") or product_id),
                "image_url": row.get("image_url"),
            }
            product_rank[product_id] = int(row.get("observed_locations") or 0)
        for row in candidates:
            product_id = str(row.get("benchmark_product_id") or "")
            if not product_id:
                continue
            product_rows.setdefault(
                product_id,
                {
                    "id": product_id,
                    "name": str(row.get("benchmark_product_name") or product_id),
                    "image_url": row.get("benchmark_image_url"),
                },
            )
            product_rank[product_id] = max(
                product_rank.get(product_id, 0),
                int(row.get("geographies") or row.get("matches") or 0),
            )
        if not product_rows:
            raise LookupError("no decision-ready benchmark products are available")
        product_options = sorted(
            product_rows.values(),
            key=lambda row: (-product_rank[str(row["id"])], str(row["name"]).casefold()),
        )
        if benchmark_product_id and benchmark_product_id not in product_rows:
            raise LookupError(
                "the selected benchmark product is not available for this retailer "
                "and comparison basis"
            )
        selected_product_id = benchmark_product_id or str(product_options[0]["id"])
        selected_candidates = [
            row for row in candidates if str(row.get("benchmark_product_id")) == selected_product_id
        ]
        relationship_index = {
            (
                str(row.get("competitor_id")),
                str(row.get("benchmark_product_id")),
                str(row.get("competitor_product_id")),
            ): row
            for row in report.get("match_relationships", [])
            if isinstance(row, dict)
        }
        selected_basis = basis_index.get(selected_profile, {})
        relationships: list[ProductLeadershipRelationship] = []
        for row in selected_candidates:
            pair_key = (
                str(row["competitor"]),
                selected_product_id,
                str(row["competitor_product_id"]),
            )
            source = relationship_index.get(pair_key, {})
            comparison_metric = str(
                row.get("comparison_metric")
                or selected_basis.get("comparison_metric")
                or "package_price"
            )
            relationships.append(
                ProductLeadershipRelationship(
                    relationship_id=str(
                        row.get("relationship_id") or source.get("relationship_id") or row.get("id")
                    ),
                    competitor_id=pair_key[0],
                    competitor_name=competitor_name_index.get(pair_key[0], pair_key[0]),
                    benchmark_product_id=selected_product_id,
                    competitor_product_id=pair_key[2],
                    profile_id=selected_profile,
                    profile_label=str(
                        row.get("profile_label") or selected_basis.get("label") or selected_profile
                    ),
                    comparison_metric=comparison_metric,
                    comparison_unit=str(
                        selected_basis.get("price_unit") or _unit(comparison_metric)
                    ),
                    scope_mode=str(source.get("scope_mode") or "global"),
                    benchmark_location_scope_keys=tuple(
                        str(value) for value in source.get("benchmark_location_scope_keys", [])
                    ),
                )
            )
        comparison_metrics = {row.comparison_metric for row in relationships}
        if len(comparison_metrics) > 1:
            raise ValueError("selected relationships do not share one comparison metric")
        comparison_metric = (
            next(iter(comparison_metrics))
            if comparison_metrics
            else str(selected_basis.get("comparison_metric") or "package_price")
        )
        comparison_unit = str(selected_basis.get("price_unit") or _unit(comparison_metric))

        competitor_products: dict[str, set[str]] = {}
        for relationship in relationships:
            competitor_products.setdefault(relationship.competitor_id, set()).add(
                relationship.competitor_product_id
            )
        competitor_retailers = sorted(competitor_products)
        observation_groups = await asyncio.gather(
            self._prices.product_observations_for_products(
                analysis_id,
                retailer_id=str(benchmark["id"]),
                product_ids=[selected_product_id],
                comparison_metric=comparison_metric,
            ),
            *(
                self._prices.product_observations_for_products(
                    analysis_id,
                    retailer_id=competitor_retailer_id,
                    product_ids=sorted(competitor_products[competitor_retailer_id]),
                    comparison_metric=comparison_metric,
                )
                for competitor_retailer_id in competitor_retailers
            ),
        )
        benchmark_observations = list(observation_groups[0].get(selected_product_id, ()))
        competitor_observations = [
            observation
            for group in observation_groups[1:]
            for observations in group.values()
            for observation in observations
        ]
        if not benchmark_observations:
            raise LookupError("positive benchmark Search observations are unavailable")

        pack = await self._packs.load(
            analysis.product_pack_id,
            analysis.product_pack_version,
        )
        parity_tolerance = float(
            pack.document.get("qa_rules", {}).get("parity_tolerance_dollars", 0.01)
        )
        benchmark_median = median(
            observation.comparison_value for observation in benchmark_observations
        )
        at_risk_threshold = max(parity_tolerance * 2, benchmark_median * 0.02)
        profile_options = [
            {
                "id": value,
                "name": str(basis_index.get(value, {}).get("label") or value),
            }
            for value in sorted(available_profiles)
        ]
        visible_competitors = [
            row
            for row in configured_competitors
            if competitor_id == "all" or str(row["id"]) == competitor_id
        ]
        result = self._projector.build(
            analysis_id=analysis.analysis_id,
            generated_at=str(report["generated_at"]),
            benchmark_retailer=benchmark,
            benchmark_product={
                **product_rows[selected_product_id],
                "name": benchmark_observations[0].product_name,
                "image_url": benchmark_observations[0].image_url,
            },
            benchmark_observations=benchmark_observations,
            competitor_observations=competitor_observations,
            relationships=relationships,
            competitor_options=visible_competitors,
            product_options=product_options,
            profile_options=profile_options,
            selected_competitor=competitor_id,
            selected_profile=selected_profile,
            radius_miles=radius_miles,
            state=state,
            city=city,
            parity_tolerance=parity_tolerance,
            at_risk_threshold=at_risk_threshold,
            comparison_metric=comparison_metric,
            comparison_unit=comparison_unit,
        )
        validate_instance(
            self._root,
            "competitive-product-leadership.schema.json",
            result,
            label=f"competitive-product-leadership:{analysis.analysis_id}",
        )
        try:
            certify_competitive_product_leadership(result).require_ready()
        except ValueError as exc:
            raise RuntimeError(f"Product Leadership trust certification failed: {exc}") from exc
        if len(self._cache) >= 96:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = result
        return result


def get_competitive_product_leadership_service(
    request: Request,
) -> CompetitiveProductLeadershipService:
    existing = getattr(request.app.state, "competitive_product_leadership_service", None)
    if existing is not None:
        return existing
    root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
    engine = request.app.state.database_probe.engine
    service = CompetitiveProductLeadershipService(
        repository_root=root,
        analyses=get_analysis_service(request),
        price_monitoring=get_price_monitoring_service(request),
        product_packs=CatalogProductPackLoader(root, PostgresProductPackCatalog(engine)),
        repository=PostgresCompetitiveLeadershipRepository(engine),
    )
    request.app.state.competitive_product_leadership_service = service
    return service


ServiceDependency = Annotated[
    CompetitiveProductLeadershipService,
    Depends(get_competitive_product_leadership_service),
]


def _require_internal_materialization_token(provided: str | None) -> None:
    expected = os.getenv("RCI_INTERNAL_SERVICE_TOKEN", "").strip()
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated internal service access is required.",
        )


@router.post("/internal/analyses/{analysis_id}/competitive-portfolios/materialize")
async def materialize_competitive_portfolios(
    analysis_id: str,
    service: ServiceDependency,
    x_rci_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_internal_materialization_token(x_rci_internal_token)
    try:
        documents = await service.pre_materialize_portfolios(analysis_id, refresh=True)
        return {
            "status": "materialized",
            "portfolio_count": len(documents),
            "provider_calls_queued": 0,
        }
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}/competitive-portfolio-scorecards")
async def competitive_portfolio_scorecards_view(
    analysis_id: str,
    service: ServiceDependency,
    competitor: str = "all",
    profile: str | None = None,
    radius_miles: int = Query(default=3, ge=1, le=5),
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
) -> dict[str, Any]:
    try:
        if radius_miles not in {1, 3, 5}:
            raise ValueError("competitive radius must be 1, 3, or 5 miles")
        return await service.portfolio_view(
            analysis_id,
            competitor_id=competitor,
            profile_id=profile,
            radius_miles=cast(Literal[1, 3, 5], radius_miles),
            state=state_filter,
            city=city,
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/analyses/{analysis_id}/competitive-product-coverage")
async def competitive_product_coverage_view(
    analysis_id: str,
    service: ServiceDependency,
    competitor: str,
    profile: str | None = None,
    radius_miles: int = Query(default=3, ge=1, le=5),
) -> dict[str, Any]:
    try:
        if radius_miles not in {1, 3, 5}:
            raise ValueError("competitive radius must be 1, 3, or 5 miles")
        return await service.product_coverage_view(
            analysis_id,
            competitor_id=competitor,
            profile_id=profile,
            radius_miles=cast(Literal[1, 3, 5], radius_miles),
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/analyses/{analysis_id}/competitive-decision-quality")
async def competitive_decision_quality_view(
    analysis_id: str,
    service: ServiceDependency,
) -> dict[str, Any]:
    try:
        return await service.decision_quality_view(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}/competitive-product-leadership")
async def competitive_product_leadership_view(
    analysis_id: str,
    service: ServiceDependency,
    competitor: str = "all",
    profile: str | None = None,
    product: str | None = None,
    radius_miles: int = Query(default=3, ge=1, le=5),
    state_filter: str | None = Query(default=None, alias="state"),
    city: str | None = None,
) -> dict[str, Any]:
    try:
        if radius_miles not in {1, 3, 5}:
            raise ValueError("competitive radius must be 1, 3, or 5 miles")
        return await service.view(
            analysis_id,
            competitor_id=competitor,
            profile_id=profile,
            benchmark_product_id=product,
            radius_miles=cast(Literal[1, 3, 5], radius_miles),
            state=state_filter,
            city=city,
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
