"""Immutable S3-compatible storage for historical source files."""

from __future__ import annotations

import asyncio
from typing import Any

from rci_analytics.historical import (
    PreparedHistoricalArtifact,
    StoredHistoricalArtifact,
    historical_object_key,
)


class S3HistoricalObjectStore:
    def __init__(self, *, bucket: str, client: Any) -> None:
        if not bucket:
            raise ValueError("OBJECT_STORAGE_BUCKET is required")
        self.bucket = bucket
        self._client = client

    @classmethod
    def create(
        cls,
        *,
        bucket: str,
        endpoint_url: str | None,
        region_name: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
        force_path_style: bool = True,
    ) -> S3HistoricalObjectStore:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region_name or None,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
            config=Config(s3={"addressing_style": "path" if force_path_style else "virtual"}),
        )
        return cls(bucket=bucket, client=client)

    async def put(
        self,
        artifact: PreparedHistoricalArtifact,
        *,
        manifest_checksum: str,
    ) -> StoredHistoricalArtifact:
        key = historical_object_key(artifact, manifest_checksum=manifest_checksum)

        def put_once() -> None:
            try:
                with artifact.path.open("rb") as source:
                    self._client.put_object(
                        Bucket=self.bucket,
                        Key=key,
                        Body=source,
                        ContentType=artifact.spec.content_type,
                        IfNoneMatch="*",
                        Metadata={
                            "sha256": artifact.checksum,
                            "row-count": str(artifact.row_count),
                            "retailer-id": artifact.spec.retailer_id,
                            "input-manifest": manifest_checksum,
                        },
                    )
            except Exception as exc:
                response = getattr(exc, "response", {})
                error = response.get("Error", {}) if isinstance(response, dict) else {}
                code = str(error.get("Code", "")) if isinstance(error, dict) else ""
                if code not in {"PreconditionFailed", "412"}:
                    raise
                existing = self._client.head_object(Bucket=self.bucket, Key=key)
                metadata = existing.get("Metadata", {})
                if not isinstance(metadata, dict) or metadata.get("sha256") != artifact.checksum:
                    raise RuntimeError(f"immutable historical object collision at {key}") from exc

        await asyncio.to_thread(put_once)
        return StoredHistoricalArtifact(
            ordinal=artifact.spec.ordinal,
            retailer_id=artifact.spec.retailer_id,
            adapter_id=artifact.spec.adapter_id,
            source_name=artifact.spec.source_name,
            source_format=artifact.spec.source_format,
            storage_uri=f"s3://{self.bucket}/{key}",
            content_type=artifact.spec.content_type,
            checksum=artifact.checksum,
            row_count=artifact.row_count,
            byte_size=artifact.byte_size,
            columns=artifact.columns,
        )
