"""Validate or import a checksummed historical source manifest."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from rci_analytics import (
    HistoricalImportService,
    HistoricalInputManifestLoader,
    PostgresAnalysisInputRepository,
    S3HistoricalObjectStore,
    prepare_historical_import,
)
from rci_analytics.historical import PreparedHistoricalImport
from rci_core import APP_VERSION, AppSettings
from rci_db import DatabaseProbe


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and enqueue an immutable historical analysis input set."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())),
    )
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    return parser.parse_args()


async def _import(
    args: argparse.Namespace, prepared: PreparedHistoricalImport
) -> dict[str, object]:
    settings = AppSettings.from_env()
    database = DatabaseProbe(settings.database_url)
    try:
        store = S3HistoricalObjectStore.create(
            bucket=os.environ["OBJECT_STORAGE_BUCKET"],
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT"),
            region_name=os.getenv("OBJECT_STORAGE_REGION"),
            access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
            force_path_style=_enabled(os.getenv("OBJECT_STORAGE_FORCE_PATH_STYLE"), default=True),
        )
        record = await HistoricalImportService(
            store,
            PostgresAnalysisInputRepository(database.engine),
            code_version=settings.app_version or APP_VERSION,
            max_attempts=args.max_attempts,
        ).import_prepared(prepared)
        return {
            "status": "queued",
            "created": record.created,
            "input_set_id": record.input_set_id,
            "collection_run_id": record.collection_run_id,
            "analysis_run_id": record.analysis_run_id,
            "manifest_checksum": record.manifest_checksum,
            "total_rows": record.total_rows,
        }
    finally:
        await database.dispose()


def main() -> None:
    args = _arguments()
    if not 1 <= args.max_attempts <= 10:
        raise ValueError("--max-attempts must be between 1 and 10")
    repository_root = args.repository_root.resolve(strict=True)
    manifest = HistoricalInputManifestLoader(repository_root).load(
        args.manifest.resolve(strict=True)
    )
    prepared = prepare_historical_import(manifest, args.source_root)
    if args.validate_only:
        result: dict[str, object] = {
            "status": "validated",
            "stable_key": manifest.stable_key,
            "product_pack": {
                "id": manifest.product_pack_id,
                "version": manifest.product_pack_version,
            },
            "manifest_checksum": prepared.manifest_checksum,
            "artifact_count": len(prepared.artifacts),
            "total_rows": prepared.total_rows,
            "artifacts": [
                {
                    "source_name": artifact.spec.source_name,
                    "retailer_id": artifact.spec.retailer_id,
                    "checksum": artifact.checksum,
                    "row_count": artifact.row_count,
                    "byte_size": artifact.byte_size,
                }
                for artifact in prepared.artifacts
            ],
        }
    else:
        result = asyncio.run(_import(args, prepared))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
