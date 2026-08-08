"""Generic location expansion and maximum-credit estimation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from rci_collections.catalog import CollectionRetailerCatalog
from rci_collections.models import (
    CollectionPlan,
    CostEstimate,
    JsonObject,
    LocationUnit,
    QueueTask,
    RetailerEstimate,
    TaskSeed,
)
from rci_collections.ports import LocationUniverseRepository
from rci_locations.normalization import normalize_country, normalize_zipcode


def canonical_checksum(document: JsonObject) -> str:
    encoded = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def request_fingerprint(payload: JsonObject) -> str:
    return canonical_checksum(payload)


def _object(value: Any, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _objects(value: Any, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _deduplicated_zipcodes(rows: Iterable[LocationUnit]) -> list[str]:
    return sorted({row.zipcode for row in rows if row.zipcode})


class CollectionPlanner:
    def __init__(
        self,
        universe: LocationUniverseRepository,
        retailer_catalog: CollectionRetailerCatalog,
        *,
        max_attempts: int = 5,
    ) -> None:
        if not 1 <= max_attempts <= 20:
            raise ValueError("max attempts must be between 1 and 20")
        self._universe = universe
        self._catalog = retailer_catalog
        self._max_attempts = max_attempts

    async def plan(self, config: JsonObject) -> CollectionPlan:
        geography = _object(config.get("geography"), "geography")
        pagination = _object(config.get("pagination"), "pagination")
        query = _object(config.get("query"), "query")
        retailers = [
            item
            for item in _objects(config.get("retailers"), "retailers")
            if bool(item.get("enabled"))
        ]
        if not retailers:
            raise ValueError("at least one retailer must be enabled")

        country = normalize_country(geography.get("country", "USA"))
        benchmark_retailer = str(
            geography.get("benchmark_retailer") or config.get("benchmark_retailer")
        )
        capabilities = {
            str(item["retailer_id"]): self._catalog.get(str(item["retailer_id"]))
            for item in retailers
        }
        source_ids = {
            retailer_id
            for retailer_id, capability in capabilities.items()
            if capability.location_dimension == "store_zip"
        }
        source_ids.add(benchmark_retailer)
        rows = await self._universe.list_location_units(sorted(source_ids), country)
        by_retailer: dict[str, list[LocationUnit]] = defaultdict(list)
        for row in rows:
            by_retailer[row.retailer_id].append(row)

        strategy = str(geography["strategy"])
        states = {state.upper() for state in _strings(geography.get("states"))}
        explicit_zips = {
            normalized
            for raw in _strings(geography.get("zipcodes"))
            for normalized in [normalize_zipcode(raw, country)]
            if normalized is not None
        }
        explicit_location_ids = set(_strings(geography.get("location_ids")))
        benchmark_rows = by_retailer.get(benchmark_retailer, [])
        benchmark_zips = set(_deduplicated_zipcodes(benchmark_rows))
        union_rows = [
            row for retailer_id in capabilities for row in by_retailer.get(retailer_id, [])
        ]
        union_zips = set(_deduplicated_zipcodes(union_rows))

        all_tasks: list[TaskSeed] = []
        estimates: list[RetailerEstimate] = []
        default_pages = int(pagination["max_pages"])
        stop_on_empty = bool(pagination["stop_on_empty"])
        stop_on_short_page = bool(pagination.get("stop_on_short_page", False))
        for retailer in retailers:
            retailer_id = str(retailer["retailer_id"])
            capability = capabilities[retailer_id]
            max_pages = int(retailer.get("max_pages_override") or default_pages)
            if not 1 <= max_pages <= 10:
                raise ValueError("max pages must be between 1 and 10")

            if capability.location_dimension == "store_zip":
                location_units = self._select_store_units(
                    by_retailer.get(retailer_id, []),
                    strategy=strategy,
                    states=states,
                    explicit_zips=explicit_zips,
                    explicit_location_ids=explicit_location_ids,
                    benchmark_zips=benchmark_zips,
                    union_zips=union_zips,
                )
                tasks = [
                    self._store_task(
                        unit,
                        retailer,
                        query,
                        max_pages,
                        stop_on_empty,
                        stop_on_short_page,
                        capability.credits_per_successful_page,
                        self._max_attempts,
                    )
                    for unit in location_units
                    if unit.zipcode is not None
                ]
            elif capability.location_dimension == "zipcode":
                zipcodes = self._select_zip_units(
                    strategy=strategy,
                    states=states,
                    explicit_zips=explicit_zips,
                    explicit_location_ids=explicit_location_ids,
                    benchmark_rows=benchmark_rows,
                    union_zips=union_zips,
                    all_rows=rows,
                )
                tasks = [
                    self._zip_task(
                        zipcode,
                        retailer,
                        query,
                        max_pages,
                        stop_on_empty,
                        stop_on_short_page,
                        capability.credits_per_successful_page,
                        self._max_attempts,
                    )
                    for zipcode in zipcodes
                ]
            else:
                raise ValueError(
                    f"retailer {retailer_id} has unverified location dimension "
                    f"{capability.location_dimension!r}"
                )

            location_count = len(tasks)
            estimated_pages = location_count * max_pages
            estimated_credits = estimated_pages * capability.credits_per_successful_page
            estimates.append(
                RetailerEstimate(
                    retailer_id=retailer_id,
                    location_units=location_count,
                    credits_per_page=capability.credits_per_successful_page,
                    max_pages=max_pages,
                    estimated_pages=estimated_pages,
                    estimated_credits=estimated_credits,
                )
            )
            all_tasks.extend(tasks)

        estimate = CostEstimate(
            definition_id=str(config["id"]),
            retailers=tuple(estimates),
            estimated_total_pages=sum(item.estimated_pages for item in estimates),
            estimated_total_credits=sum(item.estimated_credits for item in estimates),
        )
        return CollectionPlan(estimate=estimate, initial_tasks=tuple(all_tasks))

    @staticmethod
    def _select_store_units(
        rows: list[LocationUnit],
        *,
        strategy: str,
        states: set[str],
        explicit_zips: set[str],
        explicit_location_ids: set[str],
        benchmark_zips: set[str],
        union_zips: set[str],
    ) -> list[LocationUnit]:
        if strategy == "all_retailer_locations":
            selected = rows
        elif strategy == "states":
            selected = [row for row in rows if row.state and row.state.upper() in states]
        elif strategy == "custom_zips":
            selected = [row for row in rows if row.zipcode in explicit_zips]
        elif strategy == "custom_locations":
            selected = [row for row in rows if row.id in explicit_location_ids]
        elif strategy == "benchmark_retailer_zips":
            selected = [row for row in rows if row.zipcode in benchmark_zips]
        elif strategy == "union_retailer_zips":
            selected = [row for row in rows if row.zipcode in union_zips]
        else:
            raise ValueError(f"unsupported geography strategy {strategy!r}")
        return sorted(selected, key=lambda item: (item.store_number, item.id))

    @staticmethod
    def _select_zip_units(
        *,
        strategy: str,
        states: set[str],
        explicit_zips: set[str],
        explicit_location_ids: set[str],
        benchmark_rows: list[LocationUnit],
        union_zips: set[str],
        all_rows: list[LocationUnit],
    ) -> list[str]:
        if strategy == "custom_zips":
            zipcodes = explicit_zips
        elif strategy == "custom_locations":
            zipcodes = {
                row.zipcode for row in all_rows if row.id in explicit_location_ids and row.zipcode
            }
        elif strategy == "states":
            zipcodes = {
                row.zipcode
                for row in benchmark_rows
                if row.zipcode and row.state and row.state.upper() in states
            }
        elif strategy == "union_retailer_zips":
            zipcodes = union_zips
        elif strategy in {"all_retailer_locations", "benchmark_retailer_zips"}:
            zipcodes = {row.zipcode for row in benchmark_rows if row.zipcode}
        else:
            raise ValueError(f"unsupported geography strategy {strategy!r}")
        return sorted(zipcodes)

    @staticmethod
    def _base_payload(
        retailer: JsonObject,
        query: JsonObject,
        *,
        zipcode: str,
        store_number: str | None,
    ) -> JsonObject:
        return {
            "retailer_id": str(retailer["retailer_id"]),
            "adapter_id": str(retailer["adapter_id"]),
            "keyword": str(query["keyword"]),
            "amazon_same_day_url_template": query.get("amazon_same_day_url_template"),
            "zipcode": zipcode,
            "store_number": store_number,
            "sort": retailer.get("sort"),
            "page": 1,
            "request_overrides": retailer.get("request_overrides", {}),
        }

    @classmethod
    def _store_task(
        cls,
        unit: LocationUnit,
        retailer: JsonObject,
        query: JsonObject,
        max_pages: int,
        stop_on_empty: bool,
        stop_on_short_page: bool,
        credits_per_success: int,
        max_attempts: int,
    ) -> TaskSeed:
        assert unit.zipcode is not None
        payload = cls._base_payload(
            retailer, query, zipcode=unit.zipcode, store_number=unit.store_number
        )
        return TaskSeed(
            retailer_id=str(retailer["retailer_id"]),
            retailer_location_id=unit.id,
            adapter_id=str(retailer["adapter_id"]),
            location_scope_key=f"location:{unit.id}",
            zipcode=unit.zipcode,
            store_number=unit.store_number,
            page_number=1,
            max_pages=max_pages,
            stop_on_empty=stop_on_empty,
            stop_on_short_page=stop_on_short_page,
            credits_per_success=credits_per_success,
            request_payload=payload,
            request_fingerprint=request_fingerprint(payload),
            max_attempts=max_attempts,
        )

    @classmethod
    def _zip_task(
        cls,
        zipcode: str,
        retailer: JsonObject,
        query: JsonObject,
        max_pages: int,
        stop_on_empty: bool,
        stop_on_short_page: bool,
        credits_per_success: int,
        max_attempts: int,
    ) -> TaskSeed:
        payload = cls._base_payload(retailer, query, zipcode=zipcode, store_number=None)
        return TaskSeed(
            retailer_id=str(retailer["retailer_id"]),
            retailer_location_id=None,
            adapter_id=str(retailer["adapter_id"]),
            location_scope_key=f"zip:{zipcode}",
            zipcode=zipcode,
            store_number=None,
            page_number=1,
            max_pages=max_pages,
            stop_on_empty=stop_on_empty,
            stop_on_short_page=stop_on_short_page,
            credits_per_success=credits_per_success,
            request_payload=payload,
            request_fingerprint=request_fingerprint(payload),
            max_attempts=max_attempts,
        )


def next_page_seed(task: QueueTask) -> TaskSeed | None:
    if task.page_number >= task.max_pages:
        return None
    payload = dict(task.request_payload)
    page_number = task.page_number + 1
    payload["page"] = page_number
    return TaskSeed(
        retailer_id=task.retailer_id,
        retailer_location_id=task.retailer_location_id,
        adapter_id=task.adapter_id,
        location_scope_key=task.location_scope_key,
        zipcode=task.zipcode,
        store_number=task.store_number,
        page_number=page_number,
        max_pages=task.max_pages,
        stop_on_empty=task.stop_on_empty,
        stop_on_short_page=task.stop_on_short_page,
        credits_per_success=task.credits_per_success,
        request_payload=payload,
        request_fingerprint=request_fingerprint(payload),
        max_attempts=task.max_attempts,
    )
