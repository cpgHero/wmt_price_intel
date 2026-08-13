"""Catalog-driven MetricsCart V1 retailer adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from rci_collections.models import QueueTask
from rci_providers.extraction import extract_result_array
from rci_providers.models import JsonObject, ProviderRequest, RetailerSpec

ADAPTER_IDS = {
    "metricscart_walmart_search_zipcode_v2": "walmart_us",
    "metricscart_new_aldi_serp_zipcode": "aldi_us",
    "metricscart_amazon_same_day_zipcode": "amazon_us_same_day",
}
PROTECTED_OVERRIDES = {"x-api-key", "page", "zipcode", "store"}


class MetricsCartRetailerAdapter:
    def __init__(self, adapter_id: str, spec: RetailerSpec) -> None:
        self.id = adapter_id
        self.retailer_id = spec.retailer_id
        self.spec = spec
        self.credits_per_successful_page = spec.credits_per_successful_page

    def build_request(self, task: QueueTask) -> ProviderRequest:
        if task.retailer_id != self.retailer_id:
            raise ValueError(f"adapter {self.id} cannot handle retailer {task.retailer_id!r}")
        if task.credits_per_success != self.credits_per_successful_page:
            raise ValueError(
                f"task credit value {task.credits_per_success} does not match catalog value "
                f"{self.credits_per_successful_page} for {self.retailer_id}"
            )
        payload = task.request_payload
        keyword = str(payload.get("keyword") or "").strip()
        params: JsonObject = {
            "zipcode": task.zipcode,
            "page": task.page_number,
        }
        if self.retailer_id == "amazon_us_same_day":
            template = payload.get("amazon_same_day_url_template")
            if not isinstance(template, str) or not template.strip():
                raise ValueError("Amazon Same Day requires amazon_same_day_url_template")
            params["url"] = template.replace("{{keyword}}", quote_plus(keyword))
        else:
            if not keyword:
                raise ValueError(f"{self.retailer_id} requires a keyword")
            params["keyword"] = keyword
            if task.store_number is None:
                raise ValueError(f"{self.retailer_id} requires a store number")
            params["store"] = task.store_number

        sort = payload.get("sort") or self.spec.default_sort
        if sort:
            params["sort"] = str(sort)
        overrides = payload.get("request_overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError("request_overrides must be an object")
        protected = PROTECTED_OVERRIDES.intersection(overrides)
        if protected:
            raise ValueError(
                f"request_overrides cannot set protected parameters: {', '.join(sorted(protected))}"
            )
        params.update({str(key): value for key, value in overrides.items() if value is not None})
        missing = [name for name in self.spec.required_params if not params.get(name)]
        if missing:
            raise ValueError(f"missing required provider parameters: {', '.join(missing)}")
        return ProviderRequest(method=self.spec.method, path=self.spec.endpoint, params=params)

    def extract_result_array(self, payload: Any) -> list[JsonObject]:
        return extract_result_array(payload)

    def normalize_result(self, result: JsonObject, task: QueueTask) -> JsonObject:
        identifiers = result.get("product_identifiers")
        return {
            "retailer_id": self.retailer_id,
            "source_retailer": result.get("retailer"),
            "result_position": result.get("result_position"),
            "name": result.get("name"),
            "brand": result.get("brand"),
            "price": result.get("price"),
            "price_regular": result.get("price_regular"),
            "price_discounted": result.get("price_discounted"),
            "rating": result.get("rating"),
            "rating_count": result.get("rating_count") or result.get("reviews_count"),
            "retailer_product_id": (
                str(result["retailer_product_id"])
                if result.get("retailer_product_id") is not None
                else None
            ),
            "product_identifiers": dict(identifiers) if isinstance(identifiers, dict) else {},
            "url": result.get("url"),
            "image_url": result.get("image_primary"),
            "in_stock": result.get("stock_availability"),
            "zipcode": task.zipcode,
            "store_number": task.store_number,
            "page": task.page_number,
            "raw": result,
        }

    @staticmethod
    def should_queue_next_page(
        results: list[JsonObject], page: int, max_pages: int, *, stop_on_empty: bool
    ) -> bool:
        return page < max_pages and (bool(results) or not stop_on_empty)


class MetricsCartAdapterRegistry:
    def __init__(self, adapters: dict[str, MetricsCartRetailerAdapter]) -> None:
        self._adapters = adapters

    @classmethod
    def from_catalog(cls, path: Path) -> MetricsCartAdapterRegistry:
        document = json.loads(path.read_text(encoding="utf-8"))
        by_retailer = {str(item["id"]): item for item in document.get("retailers", [])}
        adapters: dict[str, MetricsCartRetailerAdapter] = {}
        for adapter_id, retailer_id in ADAPTER_IDS.items():
            item = by_retailer.get(retailer_id)
            if item is None or item.get("status") != "enabled":
                raise ValueError(f"enabled retailer {retailer_id!r} missing from catalog")
            spec = RetailerSpec(
                retailer_id=retailer_id,
                endpoint=str(item["endpoint"]),
                method=str(item.get("method", "GET")).upper(),
                credits_per_successful_page=int(item["credits_per_successful_page"]),
                location_dimension=str(item["location_dimension"]),
                required_params=tuple(str(value) for value in item.get("required_params", [])),
                aliases=tuple(str(value) for value in item.get("api_retailer_aliases", [])),
                default_sort=(str(item["default_sort"]) if item.get("default_sort") else None),
            )
            adapters[adapter_id] = MetricsCartRetailerAdapter(adapter_id, spec)
        return cls(adapters)

    def get(self, adapter_id: str) -> MetricsCartRetailerAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise ValueError(f"unsupported MetricsCart adapter {adapter_id!r}") from exc
