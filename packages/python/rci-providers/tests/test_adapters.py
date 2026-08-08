from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from rci_collections.models import QueueTask
from rci_providers.adapters import MetricsCartAdapterRegistry
from rci_providers.extraction import extract_result_array

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPOSITORY_ROOT / "config" / "retailer-catalog.json"


def _task(
    *,
    retailer_id: str,
    adapter_id: str,
    store_number: str | None,
    payload: dict[str, Any] | None = None,
) -> QueueTask:
    now = datetime.now(UTC)
    return QueueTask(
        id="00000000-0000-0000-0000-000000000101",
        collection_run_id="00000000-0000-0000-0000-000000000201",
        retailer_id=retailer_id,
        retailer_location_id=None,
        adapter_id=adapter_id,
        location_scope_key="zip:00123",
        zipcode="00123",
        store_number=store_number,
        page_number=2,
        max_pages=3,
        stop_on_empty=True,
        stop_on_short_page=False,
        credits_per_success=1 if retailer_id == "walmart_us" else 2,
        request_payload=payload
        or {
            "keyword": "fresh strawberries",
            "amazon_same_day_url_template": (
                "https://www.amazon.com/s?k={{keyword}}&i=samedaystore"
            ),
            "sort": None,
            "request_overrides": {},
        },
        request_fingerprint="fingerprint",
        status="running",
        priority=100,
        attempt_count=1,
        max_attempts=5,
        available_at=now,
        locked_by="worker",
        lease_expires_at=now + timedelta(minutes=5),
        created_at=now,
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([{"id": 1}], 1),
        ({"results": [{"id": 1}]}, 1),
        ({"items": [{"id": 1}]}, 1),
        ({"products": [{"id": 1}]}, 1),
        ({"result": {"results": [{"id": 1}]}}, 1),
        ({"result": {"items": [{"id": 1}]}}, 1),
        ({"data": {"results": [{"id": 1}]}}, 1),
        ({"data": {"items": [{"id": 1}]}}, 1),
        ({"data": [{"id": 1}, "ignored"]}, 1),
        ({"unrelated": []}, 0),
    ],
)
def test_extracts_every_supported_result_array_path(payload: object, expected: int) -> None:
    assert len(extract_result_array(payload)) == expected


def test_walmart_and_aldi_requests_preserve_string_store_ids() -> None:
    registry = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH)
    walmart = registry.get("metricscart_walmart_search_zipcode_v2").build_request(
        _task(
            retailer_id="walmart_us",
            adapter_id="metricscart_walmart_search_zipcode_v2",
            store_number="0007",
        )
    )
    aldi = registry.get("metricscart_new_aldi_serp_zipcode").build_request(
        _task(
            retailer_id="aldi_us",
            adapter_id="metricscart_new_aldi_serp_zipcode",
            store_number="36873",
        )
    )

    assert walmart.path == "/mc/walmart/search/zipcode/v2/"
    assert walmart.params == {
        "zipcode": "00123",
        "page": 2,
        "keyword": "fresh strawberries",
        "store": "0007",
        "sort": "Best Match",
    }
    assert aldi.path == "/mc/new_aldi/serp/zipcode"
    assert aldi.params["store"] == "36873"


def test_amazon_requires_and_renders_same_day_url_context() -> None:
    registry = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH)
    adapter = registry.get("metricscart_amazon_same_day_zipcode")
    request = adapter.build_request(
        _task(
            retailer_id="amazon_us_same_day",
            adapter_id="metricscart_amazon_same_day_zipcode",
            store_number=None,
        )
    )

    assert request.path == "/mc/amazon/search/zipcode/"
    assert request.params == {
        "zipcode": "00123",
        "page": 2,
        "url": "https://www.amazon.com/s?k=fresh+strawberries&i=samedaystore",
        "sort": "Featured",
    }

    task = _task(
        retailer_id="amazon_us_same_day",
        adapter_id="metricscart_amazon_same_day_zipcode",
        store_number=None,
        payload={"keyword": "strawberries", "request_overrides": {}},
    )
    with pytest.raises(ValueError, match="requires amazon_same_day_url_template"):
        adapter.build_request(task)


@pytest.mark.parametrize(
    ("adapter_id", "retailer_id", "fixture_name", "store_number"),
    [
        (
            "metricscart_walmart_search_zipcode_v2",
            "walmart_us",
            "walmart_success.json",
            "2464",
        ),
        (
            "metricscart_new_aldi_serp_zipcode",
            "aldi_us",
            "aldi_success.json",
            "473-103",
        ),
        (
            "metricscart_amazon_same_day_zipcode",
            "amazon_us_same_day",
            "amazon_success.json",
            None,
        ),
    ],
)
def test_fixture_results_normalize_to_canonical_retailers(
    adapter_id: str, retailer_id: str, fixture_name: str, store_number: str | None
) -> None:
    payload = json.loads((REPOSITORY_ROOT / "fixtures" / "api_samples" / fixture_name).read_text())
    registry = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH)
    adapter = registry.get(adapter_id)
    results = adapter.extract_result_array(payload)
    normalized = adapter.normalize_result(
        results[0],
        _task(
            retailer_id=retailer_id,
            adapter_id=adapter_id,
            store_number=store_number,
        ),
    )

    assert normalized["retailer_id"] == retailer_id
    assert normalized["retailer_product_id"]
    assert normalized["name"]
    assert normalized["zipcode"] == "00123"


def test_request_overrides_cannot_replace_auth_or_location_identity() -> None:
    registry = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH)
    adapter = registry.get("metricscart_walmart_search_zipcode_v2")
    task = _task(
        retailer_id="walmart_us",
        adapter_id="metricscart_walmart_search_zipcode_v2",
        store_number="0007",
        payload={
            "keyword": "strawberries",
            "request_overrides": {"x-api-key": "leak", "page": 9},
        },
    )

    with pytest.raises(ValueError, match="protected parameters"):
        adapter.build_request(task)
