from __future__ import annotations

from pathlib import Path

from rci_products import ProductDetailCatalog, ProductDetailJob, ProductDetailRequestContext
from rci_products.storage import S3ProductDetailRawObjectStore
from rci_providers.models import ProviderRequest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class CapturingS3Client:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    def put_object(self, **kwargs: object) -> None:
        self.request = kwargs


async def test_s3_raw_object_persists_http_status_for_recovery() -> None:
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("kroger_us")
    context = ProductDetailRequestContext(
        product_id="0001111060914",
        zipcode="72801",
        store="02500624",
    )
    job = ProductDetailJob(
        id="00000000-0000-0000-0000-000000000101",
        run_id="00000000-0000-0000-0000-000000000102",
        canonical_product_db_id="00000000-0000-0000-0000-000000000103",
        canonical_product_id="kroger_us:0001111060914",
        retailer_id="kroger_us",
        endpoint=endpoint,
        context=context,
        request_checksum=context.checksum(endpoint),
        credits_per_call=endpoint.credits_per_successful_page,
        status="running",
        attempt_count=1,
        max_attempts=3,
    )
    client = CapturingS3Client()
    store = S3ProductDetailRawObjectStore(bucket="raw-test", client=client)

    await store.put_response(
        job,
        ProviderRequest(
            method="GET",
            path=endpoint.path,
            params=context.parameters(),
        ),
        http_status=429,
        body=b'{"message":"API rate limit exceeded"}',
        response_content_type="application/json",
    )

    assert client.request is not None
    assert client.request["Metadata"]["http-status"] == "429"  # type: ignore[index]
    assert client.request["Metadata"]["response-content-type"] == "application/json"  # type: ignore[index]
