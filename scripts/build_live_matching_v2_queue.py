#!/usr/bin/env python3
"""Build and optionally import a Matching v2 queue from live collection evidence."""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import os
import re
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from botocore.config import Config
from sqlalchemy import text

from rci_analytics import MatchingV2SourceInput, build_matching_v2_evidence_profile
from rci_collections import QueueTask
from rci_core import AppSettings
from rci_db import DatabaseProbe
from rci_providers import MetricsCartAdapterRegistry

ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", action="append", required=True, dest="run_ids")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--product-pack", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--competitor", action="append", default=[])
    parser.add_argument("--profile")
    parser.add_argument("--review-queue-version", required=True)
    parser.add_argument("--decided-at", default=datetime.now(UTC).isoformat())
    parser.add_argument(
        "--repository-root", type=Path, default=Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd()))
    )
    parser.add_argument("--import-review-queue", action="store_true")
    parser.add_argument("--imported-by", default="codex-live-collection-matching-v2")
    return parser.parse_args()


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


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
        raw_artifact_id=str(row["raw_artifact_id"]) if row["raw_artifact_id"] else None,
        http_status=int(row["http_status"]) if row["http_status"] is not None else None,
        result_count=int(row["result_count"]) if row["result_count"] is not None else None,
        failure_class=str(row["failure_class"]) if row["failure_class"] is not None else None,
        billable_credits=int(row["billable_credits"]),
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        is_preflight=bool(row["is_preflight"]),
    )


def _s3_client() -> Any:
    import boto3  # type: ignore[import-untyped]

    return boto3.client(
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


def _read_object(client: Any, bucket: str, storage_uri: str, checksum: str) -> bytes:
    prefix = f"s3://{bucket}/"
    if not storage_uri.startswith(prefix):
        raise ValueError(f"artifact belongs to unexpected bucket: {storage_uri}")
    body = client.get_object(Bucket=bucket, Key=storage_uri.removeprefix(prefix))["Body"].read()
    if hashlib.sha256(body).hexdigest() != checksum:
        raise ValueError(f"artifact checksum mismatch: {storage_uri}")
    return body


def _safe(value: str) -> str:
    return _SAFE_NAME.sub("-", value).strip("-._") or "value"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({str(field) for row in rows for field in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


async def _task_rows(database: DatabaseProbe, run_ids: list[str]) -> list[dict[str, Any]]:
    async with database.engine.connect() as connection:
        rows = (
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
                    {"run_ids": run_ids},
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


async def _pdp_rows(database: DatabaseProbe, run_ids: list[str]) -> list[dict[str, Any]]:
    async with database.engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT DISTINCT ON (cp.retailer_id, cp.retailer_product_id)
                          s.id::text AS snapshot_id, cp.id::text AS canonical_product_id,
                          cp.retailer_id, cp.retailer_product_id, j.request_context, j.endpoint,
                          s.http_status, s.billable_credits, s.raw_storage_uri,
                          s.raw_checksum, s.observed_at
                        FROM canonical_product_context context
                        JOIN canonical_product cp ON cp.id = context.canonical_product_id
                        JOIN product_detail_snapshot s ON s.canonical_product_id = cp.id
                        JOIN product_detail_job j ON j.id = s.product_detail_job_id
                        WHERE context.organization_id::text = :organization_id
                          AND context.context->'collection_run_ids' ?| CAST(:run_ids AS text[])
                          AND s.http_status = 200 AND s.normalized
                        ORDER BY cp.retailer_id, cp.retailer_product_id,
                          s.observed_at DESC, s.id DESC
                        """
                    ),
                    {"organization_id": ORGANIZATION_ID, "run_ids": run_ids},
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def _build_pdp_archive(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    client: Any,
    bucket: str,
    product_pack_id: str,
) -> None:
    manifest_rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            compressed = _read_object(
                client, bucket, str(row["raw_storage_uri"]), str(row["raw_checksum"])
            )
            body = gzip.decompress(compressed)
            response_path = (
                f"responses/{_safe(str(row['retailer_id']))}/"
                f"{_safe(str(row['retailer_product_id']))}/"
                f"{_safe(str(row['snapshot_id']))}.json"
            )
            archive.writestr(response_path, body)
            manifest_rows.append(
                {
                    **row,
                    "observed_at": row["observed_at"].isoformat(),
                    "response_file": response_path,
                }
            )
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "analysis": {"product_pack_id": product_pack_id},
                    "snapshots": manifest_rows,
                },
                indent=2,
                default=str,
            ),
        )


async def _import_queue(
    root: Path, database: DatabaseProbe, queue: dict[str, Any], by: str
) -> dict[str, Any]:
    from rci_api.matching_v2_review import (
        ImportReviewQueueRequest,
        MatchingV2ReviewService,
        PostgresMatchingV2ReviewRepository,
    )

    service = MatchingV2ReviewService(PostgresMatchingV2ReviewRepository(database.engine), root)
    return await service.import_queue(
        ImportReviewQueueRequest(
            organization_id=ORGANIZATION_ID,
            imported_by=by,
            queue=queue,
        )
    )


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.repository_root.resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    settings = AppSettings.from_env()
    database = DatabaseProbe(settings.database_url)
    client = _s3_client()
    bucket = os.environ["OBJECT_STORAGE_BUCKET"]
    try:
        rows_by_retailer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        adapters = MetricsCartAdapterRegistry.from_catalog(root / "config/retailer-catalog.json")
        raw_rows = await _task_rows(database, args.run_ids)
        task_counts: Counter[str] = Counter()
        for row in raw_rows:
            if not (
                row["status"] == "succeeded"
                and row["http_status"] is not None
                and 200 <= int(row["http_status"]) <= 299
                and row["storage_uri"]
            ):
                continue
            payload = json.loads(
                gzip.decompress(
                    _read_object(client, bucket, str(row["storage_uri"]), str(row["checksum"]))
                )
            )
            task = _queue_task(row)
            adapter = adapters.get(task.adapter_id)
            for result in adapter.extract_result_array(payload):
                normalized = {
                    **result,
                    **adapter.normalize_result(result, task),
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "collected_at": row["artifact_created_at"].isoformat(),
                }
                rows_by_retailer[task.retailer_id].append(normalized)
            task_counts[task.retailer_id] += 1

        source_inputs: list[MatchingV2SourceInput] = []
        for retailer_id, rows in sorted(rows_by_retailer.items()):
            source_path = output / f"search-{_safe(retailer_id)}.csv"
            _write_csv(source_path, rows)
            source_inputs.append(MatchingV2SourceInput(source_path, retailer_id))

        pdp_rows = await _pdp_rows(database, args.run_ids)
        pdp_path = output / "live-pdp-evidence.zip"
        _build_pdp_archive(
            pdp_path,
            pdp_rows,
            client=client,
            bucket=bucket,
            product_pack_id=args.product_pack,
        )
        profile, queue = build_matching_v2_evidence_profile(
            root,
            product_pack_id=args.product_pack,
            benchmark_retailer_id=args.benchmark,
            inputs=tuple(source_inputs),
            decided_at=args.decided_at,
            profile_id=args.profile,
            competitor_retailer_ids=tuple(args.competitor),
            pdp_archives=(pdp_path,),
            review_queue_version=args.review_queue_version,
        )
        critical = [
            finding
            for finding in profile.get("quality_findings", [])
            if finding.get("severity") == "critical"
        ]
        if critical:
            raise ValueError(f"critical matching evidence findings block queue import: {critical}")
        profile_path = output / f"{args.product_pack}.evidence-profile.json"
        queue_path = output / f"{args.product_pack}.review-queue.json"
        profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        queue_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
        imported = (
            await _import_queue(root, database, queue, args.imported_by)
            if args.import_review_queue
            else None
        )
        return {
            "collection_run_ids": list(args.run_ids),
            "successful_search_tasks": dict(sorted(task_counts.items())),
            "search_rows": {key: len(value) for key, value in sorted(rows_by_retailer.items())},
            "pdp_snapshot_count": len(pdp_rows),
            "queue_id": queue["queue_id"],
            "queue_version": queue["version"],
            "queue_case_count": len(queue["cases"]),
            "quality_findings": profile.get("quality_findings", []),
            "import": imported,
        }
    finally:
        await database.dispose()


def main() -> None:
    print(json.dumps(asyncio.run(_run(_arguments())), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
