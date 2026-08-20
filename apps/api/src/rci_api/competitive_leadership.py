"""Governed benchmark-product, benchmark-store price-leadership API."""

from __future__ import annotations

import asyncio
import os
from collections import Counter
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
        self._portfolio_cache: dict[tuple[str, ...], dict[str, Any]] = {}

    async def portfolio_view(
        self,
        analysis_id: str,
        *,
        competitor_id: str,
        profile_id: str | None,
        radius_miles: Literal[1, 3, 5],
        state: str | None,
        city: str | None,
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
        if cached is not None:
            return cached

        report = await self._analyses.report_view(analysis_id)
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

        candidates = [
            row
            for row in _active_candidate_rows(report)
            if str(row.get("profile_id")) == selected_profile
            and (competitor_id == "all" or str(row.get("competitor")) == competitor_id)
        ]
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
        for competitor in visible_competitors:
            retailer_id = str(competitor["id"])
            retailer_candidates = grouped_candidates.get(retailer_id, [])
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
            for benchmark_product_id in benchmark_product_ids:
                view = projected_index.get((retailer_id, benchmark_product_id))
                if view is None:
                    continue
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
            products.sort(
                key=lambda row: (
                    -int(row["scored_product_locations"]),
                    -int(row["benchmark_product_locations"]),
                    str(row["product_name"]).casefold(),
                )
            )
            scorecards.append(
                {
                    "competitor_id": retailer_id,
                    "competitor": competitor_name_index.get(retailer_id, retailer_id),
                    "benchmark_products": len(benchmark_product_ids),
                    "competitor_products": len(competitor_product_ids),
                    "relationships": len(relationship_ids),
                    **_portfolio_summary(outcomes),
                    "products": products,
                }
            )
        scorecards.sort(
            key=lambda row: (
                -int(row["scored_product_locations"]),
                str(row["competitor"]).casefold(),
            )
        )
        result = {
            "schema_version": "1.0.0",
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
        }
        validate_instance(
            self._root,
            "competitive-portfolio-scorecards.schema.json",
            result,
            label=f"competitive-portfolio-scorecards:{analysis_id}",
        )
        if len(self._portfolio_cache) >= 32:
            self._portfolio_cache.pop(next(iter(self._portfolio_cache)))
        self._portfolio_cache[cache_key] = result
        return result

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
