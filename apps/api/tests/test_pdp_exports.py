from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO

from httpx import ASGITransport, AsyncClient

from rci_api.analyses import get_product_detail_raw_export_service
from rci_api.main import create_app
from rci_api.pdp_exports import (
    RawProductDetailExport,
    build_raw_product_detail_archive,
    source_artifact_ids,
)
from rci_core import AppSettings


def test_source_artifact_ids_are_unique_and_governed() -> None:
    assert source_artifact_ids(
        {
            "provenance": {
                "raw_source_artifact_ids": ["raw-b", "raw-a", "raw-a", None, ""],
            }
        }
    ) == ["raw-a", "raw-b"]
    assert source_artifact_ids({"provenance": {"raw_source_artifact_ids": "raw-a"}}) == []


def test_raw_product_detail_archive_preserves_provider_bodies_and_manifest() -> None:
    observed_at = datetime(2026, 8, 7, 12, 30, tzinfo=UTC)
    snapshots = [
        {
            "snapshot_id": "snapshot-200",
            "canonical_product_id": "walmart_us:123",
            "retailer_id": "walmart_us",
            "retailer_product_id": "123",
            "request_context": {"product_id": "123", "zipcode": "72712", "store": "100"},
            "endpoint": {"endpoint_id": "walmart_pdp"},
            "http_status": 200,
            "billable_credits": 1,
            "raw_storage_uri": "s3://artifacts/raw/one.json.gz",
            "raw_checksum": "a" * 64,
            "observed_at": observed_at,
        },
        {
            "snapshot_id": "snapshot-404",
            "canonical_product_id": "aldi_us:456",
            "retailer_id": "aldi_us",
            "retailer_product_id": "456",
            "request_context": {"product_id": "456", "zipcode": "72712", "store": "1-2"},
            "endpoint": {"endpoint_id": "aldi_pdp"},
            "http_status": 404,
            "billable_credits": 1,
            "raw_storage_uri": "s3://artifacts/raw/two.json.gz",
            "raw_checksum": "b" * 64,
            "observed_at": observed_at,
        },
    ]
    bodies = {
        "snapshot-200": b'{"name":"Large Grade A Eggs"}',
        "snapshot-404": b"not found",
    }
    exported = build_raw_product_detail_archive(
        analysis_id="fresh_shell_eggs-analysis",
        product_pack_id="fresh_shell_eggs",
        product_pack_version="1.1.0",
        source_ids=["raw-eggs"],
        snapshots=snapshots,
        bodies=bodies,
        generated_at=datetime(2026, 8, 15, tzinfo=UTC),
    )
    assert exported.filename == "fresh_shell_eggs_raw_pdp_20260815.zip"
    assert exported.snapshot_count == 2
    assert exported.successful_count == 1
    with zipfile.ZipFile(BytesIO(exported.body)) as bundle:
        assert bundle.read("responses/walmart_us/123/snapshot-200.json") == bodies["snapshot-200"]
        assert bundle.read("responses/aldi_us/456/snapshot-404.txt") == bodies["snapshot-404"]
        manifest = json.loads(bundle.read("manifest.json"))
    assert manifest["scope"]["provider_calls_made_for_export"] == 0
    assert manifest["summary"] == {
        "http_status_counts": {"200": 1, "404": 1},
        "retailer_counts": {"aldi_us": 1, "walmart_us": 1},
        "snapshot_count": 2,
        "successful_http_200_count": 1,
    }


async def test_raw_product_detail_export_requires_admin_token(monkeypatch) -> None:
    class ExportService:
        async def export(self, identifier: str) -> RawProductDetailExport:
            assert identifier == "fresh_shell_eggs-analysis"
            return RawProductDetailExport(
                filename="eggs.zip",
                body=b"zip-body",
                snapshot_count=3,
                successful_count=2,
            )

    monkeypatch.setenv("PRODUCT_PACK_ADMIN_TOKEN", "private-token")
    app = create_app(AppSettings(app_env="production"))
    app.dependency_overrides[get_product_detail_raw_export_service] = ExportService
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthorized = await client.get(
            "/api/v1/admin/analyses/fresh_shell_eggs-analysis/pdp-raw-export"
        )
        assert unauthorized.status_code == 401
        response = await client.get(
            "/api/v1/admin/analyses/fresh_shell_eggs-analysis/pdp-raw-export",
            headers={"X-RCI-Admin-Token": "private-token"},
        )
    assert response.status_code == 200
    assert response.content == b"zip-body"
    assert response.headers["content-disposition"] == 'attachment; filename="eggs.zip"'
    assert response.headers["x-rci-pdp-snapshot-count"] == "3"
    assert response.headers["x-rci-pdp-successful-count"] == "2"
    assert response.headers["x-rci-provider-calls"] == "0"
