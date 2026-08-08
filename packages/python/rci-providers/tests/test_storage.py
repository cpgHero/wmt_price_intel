from __future__ import annotations

import gzip
from datetime import UTC, datetime, timedelta
from typing import Any

from rci_collections.models import QueueTask
from rci_providers.models import ProviderRequest
from rci_providers.storage import S3RawObjectStore


class RecordingS3Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _task() -> QueueTask:
    now = datetime.now(UTC)
    return QueueTask(
        id="00000000-0000-0000-0000-000000000101",
        collection_run_id="00000000-0000-0000-0000-000000000201",
        retailer_id="walmart_us",
        retailer_location_id=None,
        adapter_id="metricscart_walmart_search_zipcode_v2",
        location_scope_key="zip:00123",
        zipcode="00123",
        store_number="0007",
        page_number=3,
        max_pages=3,
        stop_on_empty=True,
        stop_on_short_page=False,
        credits_per_success=1,
        request_payload={},
        request_fingerprint="fingerprint",
        status="running",
        priority=100,
        attempt_count=2,
        max_attempts=5,
        available_at=now,
        locked_by="worker",
        lease_expires_at=now + timedelta(minutes=5),
        created_at=now,
    )


async def test_s3_storage_uses_immutable_attempt_scoped_gzip_keys() -> None:
    client = RecordingS3Client()
    store = S3RawObjectStore(bucket="raw-bucket", client=client)
    artifact = await store.put_response(
        _task(),
        ProviderRequest(method="GET", path="/mc/walmart/search/zipcode/v2", params={}),
        http_status=200,
        body=b'{"results":[]}',
        response_content_type="application/json",
    )

    call = client.calls[0]
    assert call["Bucket"] == "raw-bucket"
    assert "/page=0003/attempt=0002/" in call["Key"]
    assert call["IfNoneMatch"] == "*"
    assert call["ContentEncoding"] == "gzip"
    assert gzip.decompress(call["Body"]) == b'{"results":[]}'
    assert artifact.storage_uri == f"s3://raw-bucket/{call['Key']}"
