"""Admin-only exports of retained immutable Product Details responses."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_products.storage import ProductDetailRawObjectReader
from rci_results import AnalysisResultService

_SAFE_FILENAME = re.compile(r"[^a-zA-Z0-9._-]+")


class ProductDetailExportNotFoundError(LookupError):
    """Raised when an analysis has no retained PDP response objects."""


@dataclass(frozen=True, slots=True)
class RawProductDetailExport:
    filename: str
    body: bytes
    snapshot_count: int
    successful_count: int


def _safe_filename(value: str, *, fallback: str) -> str:
    rendered = _SAFE_FILENAME.sub("-", value.strip()).strip("-._")
    return rendered[:120] or fallback


def source_artifact_ids(document: dict[str, Any]) -> list[str]:
    provenance = document.get("provenance", {})
    values = provenance.get("raw_source_artifact_ids", []) if isinstance(provenance, dict) else []
    if not isinstance(values, list):
        return []
    return sorted({value.strip() for value in values if isinstance(value, str) and value.strip()})


def _response_extension(body: bytes) -> str:
    try:
        json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "txt"
    return "json"


def build_raw_product_detail_archive(
    *,
    analysis_id: str,
    product_pack_id: str,
    product_pack_version: str,
    source_ids: list[str],
    snapshots: list[dict[str, Any]],
    bodies: dict[str, bytes],
    generated_at: datetime | None = None,
) -> RawProductDetailExport:
    now = generated_at or datetime.now(UTC)
    retailer_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    manifest_rows: list[dict[str, Any]] = []
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for snapshot in snapshots:
            snapshot_id = str(snapshot["snapshot_id"])
            body = bodies[snapshot_id]
            retailer_id = str(snapshot["retailer_id"])
            retailer_product_id = str(snapshot["retailer_product_id"])
            http_status = int(snapshot["http_status"])
            retailer_counts[retailer_id] += 1
            status_counts[str(http_status)] += 1
            path = (
                "responses/"
                f"{_safe_filename(retailer_id, fallback='retailer')}/"
                f"{_safe_filename(retailer_product_id, fallback='product')}/"
                f"{_safe_filename(snapshot_id, fallback='snapshot')}."
                f"{_response_extension(body)}"
            )
            bundle.writestr(path, body)
            request_context = snapshot.get("request_context")
            endpoint = snapshot.get("endpoint")
            manifest_rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "canonical_product_id": str(snapshot["canonical_product_id"]),
                    "retailer_id": retailer_id,
                    "retailer_product_id": retailer_product_id,
                    "http_status": http_status,
                    "billable_credits": int(snapshot["billable_credits"]),
                    "observed_at": (
                        snapshot["observed_at"].isoformat()
                        if isinstance(snapshot["observed_at"], datetime)
                        else str(snapshot["observed_at"])
                    ),
                    "request_context": request_context if isinstance(request_context, dict) else {},
                    "endpoint": endpoint if isinstance(endpoint, dict) else {},
                    "response_file": path,
                    "response_byte_size": len(body),
                    "response_checksum_sha256": hashlib.sha256(body).hexdigest(),
                    "stored_object_uri": str(snapshot["raw_storage_uri"]),
                    "stored_object_checksum_sha256": str(snapshot["raw_checksum"]),
                }
            )

        manifest = {
            "schema_version": "1.0.0",
            "generated_at": now.isoformat(),
            "analysis": {
                "analysis_id": analysis_id,
                "product_pack_id": product_pack_id,
                "product_pack_version": product_pack_version,
            },
            "scope": {
                "description": (
                    "All retained PDP snapshots for canonical products linked to the "
                    "analysis source artifacts. Multiple statuses and attempts are preserved."
                ),
                "source_artifact_ids": source_ids,
                "provider_calls_made_for_export": 0,
            },
            "summary": {
                "snapshot_count": len(manifest_rows),
                "successful_http_200_count": status_counts.get("200", 0),
                "retailer_counts": dict(sorted(retailer_counts.items())),
                "http_status_counts": dict(sorted(status_counts.items())),
            },
            "snapshots": manifest_rows,
        }
        bundle.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8"),
        )
        bundle.writestr(
            "README.txt",
            (
                b"CPGHero Retail Competitive Intelligence - Raw PDP Export\n\n"
                b"The files under responses/ are the decompressed provider response bodies "
                b"exactly as retained by the application. manifest.json records request "
                b"context, provenance, HTTP status, billing credits, and SHA-256 checksums.\n\n"
                b"Search results remain authoritative for store-level price and observed "
                b"availability. PDP responses are identity, attribute, and contextual evidence.\n"
                b"No MetricsCart request was made to create this export.\n"
            ),
        )

    filename = f"{_safe_filename(product_pack_id, fallback='analysis')}_raw_pdp_{now:%Y%m%d}.zip"
    return RawProductDetailExport(
        filename=filename,
        body=archive.getvalue(),
        snapshot_count=len(manifest_rows),
        successful_count=status_counts.get("200", 0),
    )


class ProductDetailRawExportService:
    def __init__(
        self,
        engine: AsyncEngine,
        analysis_service: AnalysisResultService,
        reader: ProductDetailRawObjectReader,
    ) -> None:
        self._engine = engine
        self._analysis_service = analysis_service
        self._reader = reader

    async def export(self, identifier: str) -> RawProductDetailExport:
        analysis = await self._analysis_service.get(identifier)
        source_ids = source_artifact_ids(analysis.result)
        if not source_ids:
            raise ProductDetailExportNotFoundError(
                f"analysis {analysis.analysis_id!r} has no governed source-artifact references"
            )
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT DISTINCT s.id::text AS snapshot_id,
                              cp.canonical_product_id, cp.retailer_id,
                              cp.retailer_product_id, j.request_context, j.endpoint,
                              s.http_status, s.billable_credits, s.raw_storage_uri,
                              s.raw_checksum, s.observed_at
                            FROM canonical_product_context context
                            JOIN canonical_product cp
                              ON cp.id = context.canonical_product_id
                            JOIN product_detail_snapshot s
                              ON s.canonical_product_id = cp.id
                            JOIN product_detail_job j
                              ON j.id = s.product_detail_job_id
                            WHERE context.context->>'source_artifact_id' = ANY(
                              CAST(:source_artifact_ids AS text[])
                            )
                            ORDER BY cp.retailer_id, cp.retailer_product_id,
                              s.observed_at, s.id::text
                            """
                        ),
                        {"source_artifact_ids": source_ids},
                    )
                )
                .mappings()
                .all()
            )
        snapshots = [dict(row) for row in rows]
        if not snapshots:
            raise ProductDetailExportNotFoundError(
                f"analysis {analysis.analysis_id!r} has no retained PDP snapshots"
            )
        bodies: dict[str, bytes] = {}
        for snapshot in snapshots:
            snapshot_id = str(snapshot["snapshot_id"])
            bodies[snapshot_id] = await self._reader.get_response(
                str(snapshot["raw_storage_uri"]),
                expected_checksum=str(snapshot["raw_checksum"]),
            )
        return build_raw_product_detail_archive(
            analysis_id=analysis.analysis_id,
            product_pack_id=analysis.product_pack_id,
            product_pack_version=analysis.product_pack_version,
            source_ids=source_ids,
            snapshots=snapshots,
            bodies=bodies,
        )
