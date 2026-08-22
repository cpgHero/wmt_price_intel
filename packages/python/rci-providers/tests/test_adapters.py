from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from rci_collections.models import QueueTask
from rci_providers.adapters import MetricsCartAdapterRegistry
from rci_providers.extraction import extract_result_array, inspect_result_array

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPOSITORY_ROOT / "config" / "retailer-catalog.json"
METRICSCART_CATALOG_PATH = REPOSITORY_ROOT / "config" / "metricscart-api-catalog-20260816.json"


def _task(
    *,
    retailer_id: str,
    adapter_id: str,
    store_number: str | None,
    payload: dict[str, Any] | None = None,
    credits_per_success: int | None = None,
    max_pages: int = 3,
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
        max_pages=max_pages,
        stop_on_empty=True,
        stop_on_short_page=False,
        credits_per_success=(
            credits_per_success
            if credits_per_success is not None
            else (1 if retailer_id == "walmart_us" else 2)
        ),
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


def test_result_array_inspection_distinguishes_empty_page_from_unknown_shape() -> None:
    empty = inspect_result_array({"results": []})
    unknown = inspect_result_array({"unexpected": []})

    assert empty.recognized is True
    assert empty.path == ("results",)
    assert empty.results == []
    assert unknown.recognized is False


def test_search_response_audit_rejects_non_object_result_entries() -> None:
    adapter = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH).get(
        "metricscart_walmart_search_zipcode_v2"
    )

    with pytest.raises(ValueError, match="non-object entries"):
        adapter.audit_response(
            {
                "results": [
                    {
                        "name": "Milk",
                        "price": 3.98,
                        "retailer_product_id": "123",
                        "retailer": "walmart.com",
                        "is_sponsored": None,
                    },
                    None,
                ]
            }
        )


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


def test_all_fourteen_egg_search_adapters_are_catalog_driven() -> None:
    catalog = json.loads(CATALOG_PATH.read_text())
    enabled = [item for item in catalog["retailers"] if item.get("status") == "enabled"]
    registry = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH)

    assert len(enabled) == 14
    for item in enabled:
        adapter = registry.get(str(item["adapter_id"]))
        request = adapter.build_request(
            _task(
                retailer_id=str(item["id"]),
                adapter_id=str(item["adapter_id"]),
                store_number=(None if item["id"] == "amazon_us_same_day" else "0007"),
                credits_per_success=int(item["credits_per_successful_page"]),
                max_pages=(2 if "page" in item["supported_params"] else 1),
            )
        )

        assert request.path == item["endpoint"]
        assert set(request.params) <= set(item["supported_params"])
        assert set(item.get("required_params", [])) <= set(request.params)
        assert request.params.get("store") in {None, "0007"}


def test_endpoint_specific_search_parameters_do_not_leak() -> None:
    registry = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH)
    shoprite = registry.get("metricscart_shoprite_serp_zipcode").build_request(
        _task(
            retailer_id="shoprite_us",
            adapter_id="metricscart_shoprite_serp_zipcode",
            store_number="109",
            credits_per_success=1,
            max_pages=1,
        )
    )
    giant_eagle = registry.get("metricscart_giant_eagle_serp_zipcode").build_request(
        _task(
            retailer_id="giant_eagle_us",
            adapter_id="metricscart_giant_eagle_serp_zipcode",
            store_number="230",
            credits_per_success=2,
            max_pages=1,
        )
    )

    assert shoprite.params["shopping_type"] == "pickup"
    assert "page" not in shoprite.params
    assert "page" not in giant_eagle.params

    with pytest.raises(ValueError, match="does not support Search pagination"):
        registry.get("metricscart_giant_eagle_serp_zipcode").build_request(
            _task(
                retailer_id="giant_eagle_us",
                adapter_id="metricscart_giant_eagle_serp_zipcode",
                store_number="230",
                credits_per_success=2,
            )
        )


def test_all_fourteen_catalogued_search_samples_advertise_results() -> None:
    catalog = json.loads(CATALOG_PATH.read_text())
    provider_catalog = json.loads(METRICSCART_CATALOG_PATH.read_text())
    by_path = {item["path"]: item for item in provider_catalog["endpoints"]}
    registry = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH)

    for item in catalog["retailers"]:
        if item.get("status") != "enabled":
            continue
        endpoint = by_path[item["endpoint"]]
        registry.get(str(item["adapter_id"]))

        assert endpoint["sample_response"]["present"] is True
        assert "results" in endpoint["sample_response"]["top_level_fields"]


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
    assert normalized["price"] is not None
    assert normalized["is_sponsored"] is False
    assert normalized["in_stock"] is True


def test_search_price_is_authoritative_for_api_availability() -> None:
    registry = MetricsCartAdapterRegistry.from_catalog(CATALOG_PATH)
    adapter = registry.get("metricscart_walmart_search_zipcode_v2")
    result = {
        "name": "Great Value Strawberries, 1 lb",
        "retailer_product_id": "00123",
        "price": 3.48,
        "is_sponsored": False,
        "retailer": "walmart.com",
        "stock_availability": False,
    }

    normalized = adapter.normalize_result(
        result,
        _task(
            retailer_id="walmart_us",
            adapter_id="metricscart_walmart_search_zipcode_v2",
            store_number="0007",
        ),
    )

    assert normalized["in_stock"] is True
    assert normalized["raw"]["stock_availability"] is False


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
