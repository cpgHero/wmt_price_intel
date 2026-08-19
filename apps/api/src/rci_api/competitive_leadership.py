"""Governed benchmark-product, benchmark-store price-leadership API."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from statistics import median
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from rci_analytics import (
    CatalogProductPackLoader,
    CompetitiveProductLeadershipProjector,
    ProductLeadershipRelationship,
    certify_competitive_product_leadership,
)
from rci_api.analyses import get_analysis_service
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


class CompetitiveProductLeadershipService:
    def __init__(
        self,
        *,
        repository_root: Path,
        analyses: AnalysisResultService,
        price_monitoring: PriceMonitoringService,
        product_packs: CatalogProductPackLoader,
    ) -> None:
        self._root = repository_root
        self._analyses = analyses
        self._prices = price_monitoring
        self._packs = product_packs
        self._projector = CompetitiveProductLeadershipProjector()
        self._cache: dict[tuple[str, ...], dict[str, Any]] = {}

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

        analysis, report = await asyncio.gather(
            self._analyses.get(analysis_id),
            self._analyses.report_view(analysis_id),
        )
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
    )
    request.app.state.competitive_product_leadership_service = service
    return service


ServiceDependency = Annotated[
    CompetitiveProductLeadershipService,
    Depends(get_competitive_product_leadership_service),
]


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
