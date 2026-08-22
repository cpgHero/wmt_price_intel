"""Catalog-driven MetricsCart V1 retailer adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from rci_collections.models import QueueTask
from rci_providers.extraction import ResultArrayExtraction, inspect_result_array
from rci_providers.models import JsonObject, ProviderRequest, RetailerSpec

PROTECTED_OVERRIDES = {"x-api-key", "page", "zipcode", "store"}


class MetricsCartRetailerAdapter:
    def __init__(
        self,
        adapter_id: str,
        spec: RetailerSpec,
        response_contract: Mapping[str, Any],
        result_array_paths: tuple[tuple[str, ...], ...],
    ) -> None:
        self.id = adapter_id
        self.retailer_id = spec.retailer_id
        self.spec = spec
        self.credits_per_successful_page = spec.credits_per_successful_page
        self.response_contract = dict(response_contract)
        self.result_array_paths = result_array_paths
        aliases = self.response_contract.get("field_aliases", {})
        self.field_aliases = {
            str(canonical): tuple(str(alias) for alias in values)
            for canonical, values in aliases.items()
            if isinstance(values, list)
        }

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
        supported = set(self.spec.supported_params)
        if task.max_pages > 1 and "page" not in supported:
            raise ValueError(f"{self.retailer_id} does not support Search pagination")
        params: JsonObject = dict(self.spec.default_request_params)
        if "zipcode" in supported:
            params["zipcode"] = task.zipcode
        if "page" in supported:
            params["page"] = task.page_number
        if self.retailer_id == "amazon_us_same_day":
            template = payload.get("amazon_same_day_url_template")
            if not isinstance(template, str) or not template.strip():
                raise ValueError("Amazon Same Day requires amazon_same_day_url_template")
            params["url"] = template.replace("{{keyword}}", quote_plus(keyword))
        else:
            if not keyword:
                raise ValueError(f"{self.retailer_id} requires a keyword")
            params["keyword"] = keyword
            if "store" in supported and task.store_number is None:
                raise ValueError(f"{self.retailer_id} requires a store number")
            if "store" in supported:
                params["store"] = task.store_number

        sort = payload.get("sort") or self.spec.default_sort
        if sort and "sort" in supported:
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
        return self.inspect_result_array(payload).results

    def inspect_result_array(self, payload: Any) -> ResultArrayExtraction:
        return inspect_result_array(payload, self.result_array_paths)

    def audit_response(self, payload: Any) -> dict[str, Any]:
        """Fail closed when a billable API page no longer satisfies its mapped contract."""

        extraction = self.inspect_result_array(payload)
        if not extraction.recognized:
            top_level = sorted(payload) if isinstance(payload, dict) else []
            raise ValueError(
                f"unrecognized MetricsCart result-array shape; top-level fields={top_level[:40]}"
            )
        if extraction.source_count != len(extraction.results):
            raise ValueError(
                "MetricsCart result array contains non-object entries; "
                f"source_count={extraction.source_count}, object_count={len(extraction.results)}"
            )
        required = tuple(
            str(field) for field in self.response_contract.get("required_canonical_fields", [])
        )
        non_null = {
            str(field) for field in self.response_contract.get("non_null_canonical_fields", [])
        }
        missing_counts = {field: 0 for field in required}
        field_names: set[str] = set()
        for result in extraction.results:
            field_names.update(str(field) for field in result)
            for field in required:
                present = self._field_present(result, field)
                value = self._field(result, field)
                if field == "retailer_product_id" and value in (None, ""):
                    identifiers = self._field(result, "product_identifiers")
                    value = self._identifier(identifiers)
                    present = present or value not in (None, "")
                if not present or (
                    field in non_null
                    and (value is None or (isinstance(value, str) and not value.strip()))
                ):
                    missing_counts[field] += 1
            sponsored = self._field(result, "is_sponsored")
            if sponsored is not None and not isinstance(sponsored, bool):
                raise ValueError("MetricsCart is_sponsored must be boolean or null")
            price = self._field(result, "price")
            if price is not None and self._decimal(price) is None:
                raise ValueError("MetricsCart price is not numeric")
        failures = {field: count for field, count in missing_counts.items() if count}
        if failures:
            raise ValueError(
                "MetricsCart result fields do not satisfy the mapped Search contract: "
                + ", ".join(f"{field} missing in {count}" for field, count in failures.items())
            )
        return {
            "contract_version": str(self.response_contract.get("schema_version") or "unknown"),
            "result_path": ("$" if extraction.path == () else ".".join(extraction.path or ())),
            "result_count": len(extraction.results),
            "result_field_names": sorted(field_names),
            "availability_authority": self.response_contract.get("availability_authority"),
            "sponsorship_authority": self.response_contract.get("sponsorship_authority"),
        }

    def normalize_result(self, result: JsonObject, task: QueueTask) -> JsonObject:
        identifiers = self._field(result, "product_identifiers")
        product_id = self._field(result, "retailer_product_id") or self._identifier(identifiers)
        price = self._field(result, "price")
        return {
            "retailer_id": self.retailer_id,
            "source_retailer": self._field(result, "retailer"),
            "result_position": self._field(result, "result_position"),
            "name": self._field(result, "name"),
            "brand": self._field(result, "brand"),
            "price": price,
            "price_regular": self._field(result, "price_regular"),
            "price_discounted": self._field(result, "price_discounted"),
            "rating": self._field(result, "rating"),
            "rating_count": self._field(result, "rating_count"),
            "is_sponsored": self._field(result, "is_sponsored"),
            "retailer_product_id": str(product_id) if product_id is not None else None,
            "product_identifiers": dict(identifiers) if isinstance(identifiers, dict) else {},
            "url": self._field(result, "url"),
            "image_url": self._field(result, "image_primary"),
            # Search presence with a positive Search price is the governed availability rule.
            # Provider stock flags remain immutable in raw evidence for diagnosis only.
            "in_stock": bool((numeric_price := self._decimal(price)) and numeric_price > 0),
            "zipcode": task.zipcode,
            "store_number": task.store_number,
            "page": task.page_number,
            "raw": result,
        }

    def _field(self, result: Mapping[str, Any], canonical: str) -> Any:
        aliases = self.field_aliases.get(canonical, (canonical,))
        for alias in aliases:
            if alias in result and result[alias] is not None:
                return result[alias]
        return None

    def _field_present(self, result: Mapping[str, Any], canonical: str) -> bool:
        return any(alias in result for alias in self.field_aliases.get(canonical, (canonical,)))

    @staticmethod
    def _identifier(value: Any) -> Any:
        if not isinstance(value, Mapping):
            return None
        for key in ("product_id", "item_id", "asin", "upc", "sku"):
            if value.get(key) not in (None, ""):
                return value[key]
        return None

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return Decimal(str(value).replace("$", "").replace(",", "").strip())
        except (InvalidOperation, ValueError):
            return None

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
        response_contract = document.get("search_response_contract", {})
        if not isinstance(response_contract, dict):
            raise ValueError("retailer catalog search_response_contract must be an object")
        result_array_paths = tuple(
            tuple(str(value).split(".")) for value in document.get("result_array_paths", [])
        )
        if not result_array_paths:
            raise ValueError("retailer catalog must configure MetricsCart result-array paths")
        adapters: dict[str, MetricsCartRetailerAdapter] = {}
        for item in document.get("retailers", []):
            if item.get("status") != "enabled":
                continue
            retailer_id = str(item["id"])
            adapter_id = str(item.get("adapter_id") or "")
            if not adapter_id:
                raise ValueError(f"enabled retailer {retailer_id!r} has no adapter_id")
            if adapter_id in adapters:
                raise ValueError(f"duplicate MetricsCart adapter_id {adapter_id!r}")
            spec = RetailerSpec(
                retailer_id=retailer_id,
                endpoint=str(item["endpoint"]),
                method=str(item.get("method", "GET")).upper(),
                credits_per_successful_page=int(item["credits_per_successful_page"]),
                location_dimension=str(item["location_dimension"]),
                required_params=tuple(str(value) for value in item.get("required_params", [])),
                aliases=tuple(str(value) for value in item.get("api_retailer_aliases", [])),
                default_sort=(str(item["default_sort"]) if item.get("default_sort") else None),
                supported_params=tuple(str(value) for value in item.get("supported_params", [])),
                search_inputs=tuple(str(value) for value in item.get("search_inputs", ["keyword"])),
                default_request_params={
                    str(key): value for key, value in item.get("default_request_params", {}).items()
                },
            )
            adapters[adapter_id] = MetricsCartRetailerAdapter(
                adapter_id,
                spec,
                response_contract,
                result_array_paths,
            )
        return cls(adapters)

    def get(self, adapter_id: str) -> MetricsCartRetailerAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise ValueError(f"unsupported MetricsCart adapter {adapter_id!r}") from exc
