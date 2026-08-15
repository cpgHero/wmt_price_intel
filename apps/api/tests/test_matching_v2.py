from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from rci_api.main import create_app
from rci_api.matching_v2 import (
    MatchingV2ShadowArtifact,
    MatchingV2ShadowService,
    get_matching_v2_shadow_service,
)


class ShadowRepository:
    async def artifacts(self, analysis_id: str) -> list[MatchingV2ShadowArtifact]:
        assert analysis_id == "analysis-1"
        return [
            MatchingV2ShadowArtifact(
                retailer_id="aldi_us",
                storage_uri="s3://bucket/aldi.json",
                checksum="a" * 64,
                created_at="2026-08-15T10:00:00+00:00",
            ),
            MatchingV2ShadowArtifact(
                retailer_id="target_us",
                storage_uri="s3://bucket/target.json",
                checksum="b" * 64,
                created_at="2026-08-15T10:01:00+00:00",
            ),
        ]


class ShadowReader:
    async def read(self, artifact: MatchingV2ShadowArtifact) -> dict[str, object]:
        competitor = artifact.retailer_id
        return {
            "schema_version": "2.0.0-shadow",
            "competitor_retailer_id": competitor,
            "evaluated_pairs": 2,
            "edges": [
                {
                    "edge_id": f"edge-{competitor}-1",
                    "benchmark_listing_id": "walmart_us:w1",
                    "competitor_listing_id": f"{competitor}:c1",
                    "tier": "exact_specification",
                    "status": "auto_approved",
                    "attribute_evidence": [],
                },
                {
                    "edge_id": f"edge-{competitor}-2",
                    "benchmark_listing_id": "walmart_us:w2",
                    "competitor_listing_id": f"{competitor}:c2",
                    "tier": "equivalent_product",
                    "status": "candidate",
                    "attribute_evidence": [],
                },
            ],
        }


async def test_shadow_inspection_is_read_only_filterable_and_paginated() -> None:
    service = MatchingV2ShadowService(ShadowRepository(), ShadowReader())
    view = await service.view(
        "analysis-1",
        competitor_retailer_id="aldi_us",
        tier="exact_specification",
        match_status="auto_approved",
        benchmark_product_id="w1",
        competitor_product_id="c1",
        offset=0,
        limit=10,
    )

    assert view["authoritative"] is False
    assert view["report_metrics_affected"] is False
    assert view["total_edges"] == 1
    assert len(view["edges"]) == 1
    assert len(view["artifacts"]) == 1
    assert "edges" not in view["artifacts"][0]["summary"]


async def test_shadow_inspection_route_uses_bounded_limit() -> None:
    app = create_app()
    app.dependency_overrides[get_matching_v2_shadow_service] = lambda: MatchingV2ShadowService(
        ShadowRepository(), ShadowReader()
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/analyses/analysis-1/matching-v2-shadow",
            params={"competitor_retailer_id": "target_us", "limit": 1, "offset": 1},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_edges"] == 2
    assert len(body["edges"]) == 1
    assert body["edges"][0]["edge_id"] == "edge-target_us-2"
