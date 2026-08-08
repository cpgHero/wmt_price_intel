"""Immutable Parquet dataset artifact writer."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Protocol

import polars as pl

from rci_analytics.models import ClassifiedOffer, MatchRecord, NormalizedOffer
from rci_collections.models import RawArtifact

_SAFE_COMPONENT = re.compile(r"^[a-zA-Z0-9_.-]+$")


class DatasetStore(Protocol):
    async def put_bytes(self, key: str, body: bytes, *, content_type: str) -> str: ...


@dataclass(slots=True)
class InMemoryDatasetStore:
    bucket: str = "test-datasets"
    objects: dict[str, bytes] = field(default_factory=dict)

    async def put_bytes(self, key: str, body: bytes, *, content_type: str) -> str:
        del content_type
        previous = self.objects.setdefault(key, body)
        if previous != body:
            raise RuntimeError(f"immutable dataset collision at {key}")
        return f"s3://{self.bucket}/{key}"


class S3DatasetStore:
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
    ) -> S3DatasetStore:
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

    async def put_bytes(self, key: str, body: bytes, *, content_type: str) -> str:
        checksum = hashlib.sha256(body).hexdigest()

        def put_once() -> None:
            try:
                self._client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=body,
                    ContentType=content_type,
                    IfNoneMatch="*",
                    Metadata={"sha256": checksum},
                )
            except Exception as exc:
                response = getattr(exc, "response", {})
                error = response.get("Error", {}) if isinstance(response, dict) else {}
                code = str(error.get("Code", "")) if isinstance(error, dict) else ""
                if code not in {"PreconditionFailed", "412"}:
                    raise
                existing = self._client.head_object(Bucket=self.bucket, Key=key)
                metadata = existing.get("Metadata", {})
                if not isinstance(metadata, dict) or metadata.get("sha256") != checksum:
                    raise RuntimeError(f"immutable dataset collision at {key}") from exc

        await asyncio.to_thread(put_once)
        return f"s3://{self.bucket}/{key}"


class ParquetDatasetWriter:
    def __init__(self, store: DatasetStore, *, schema_version: str = "1.0.0") -> None:
        self._store = store
        self._schema_version = schema_version

    async def write_normalized(
        self,
        offers: list[NormalizedOffer],
        *,
        run_id: str,
        retailer_id: str,
        partition: int = 0,
    ) -> RawArtifact:
        return await self._write(
            [offer.to_record() for offer in offers],
            run_id=run_id,
            stage="normalized_offers",
            retailer_id=retailer_id,
            partition=partition,
        )

    async def write_classified(
        self,
        offers: list[ClassifiedOffer],
        *,
        run_id: str,
        retailer_id: str,
        partition: int = 0,
    ) -> RawArtifact:
        return await self._write(
            [offer.to_record() for offer in offers],
            run_id=run_id,
            stage="classified_offers",
            retailer_id=retailer_id,
            partition=partition,
        )

    async def write_matches(
        self,
        matches: list[MatchRecord],
        *,
        run_id: str,
        retailer_id: str,
        partition: int = 0,
    ) -> RawArtifact:
        import json

        records = [
            {
                "profile_id": match.profile_id,
                "competitor_id": match.competitor_id,
                "geography_key": match.geography_key,
                "benchmark_offer_id": match.benchmark_offer_id,
                "competitor_offer_id": match.competitor_offer_id,
                "attributes_json": json.dumps(match.attributes, sort_keys=True),
                "comparison_metric": match.comparison_metric,
                "benchmark_value": float(match.benchmark_value),
                "competitor_value": float(match.competitor_value),
                "gap": float(match.gap),
                "winner": match.winner,
                "distance_miles": match.distance_miles,
            }
            for match in matches
        ]
        return await self._write(
            records,
            run_id=run_id,
            stage="match_detail",
            retailer_id=retailer_id,
            partition=partition,
        )

    async def _write(
        self,
        records: list[dict[str, Any]],
        *,
        run_id: str,
        stage: str,
        retailer_id: str,
        partition: int,
    ) -> RawArtifact:
        for component in (run_id, stage, retailer_id):
            if not _SAFE_COMPONENT.fullmatch(component):
                raise ValueError(f"unsafe dataset key component {component!r}")
        if not records:
            raise ValueError("cannot write an empty Parquet dataset without an explicit schema")
        frame = pl.DataFrame(records, strict=False)
        output = BytesIO()
        frame.write_parquet(output, compression="zstd", statistics=True)
        body = output.getvalue()
        checksum = hashlib.sha256(body).hexdigest()
        key = (
            f"datasets/run_id={run_id}/stage={stage}/retailer_id={retailer_id}/"
            f"part-{partition:05d}-{checksum[:16]}.parquet"
        )
        uri = await self._store.put_bytes(key, body, content_type="application/vnd.apache.parquet")
        return RawArtifact(
            storage_uri=uri,
            content_type="application/vnd.apache.parquet",
            byte_size=len(body),
            checksum=checksum,
            metadata={
                "stage": stage,
                "retailer_id": retailer_id,
                "partition": partition,
                "columns": frame.columns,
            },
            artifact_type=stage,
            schema_version=self._schema_version,
            row_count=frame.height,
        )
