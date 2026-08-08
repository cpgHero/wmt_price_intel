"""REFERENCE CONTRACT ONLY. Codex should create production package structure in Phase 0."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

@dataclass(frozen=True)
class LocationUnit:
    key: str
    zipcode: str
    store_number: str | None = None
    retailer_location_id: str | None = None

@dataclass(frozen=True)
class ProviderRequest:
    method: str
    path: str
    params: dict[str, Any]

class RetailerAdapter(Protocol):
    id: str
    retailer_id: str
    credits_per_successful_page: int
    def validate_definition(self, definition: dict[str, Any]) -> list[dict[str, Any]]: ...
    def expand_location_units(self, definition: dict[str, Any], location_repo: Any) -> Iterable[LocationUnit]: ...
    def build_request(self, task: dict[str, Any], definition: dict[str, Any]) -> ProviderRequest: ...
    def extract_result_array(self, payload: Any) -> list[dict[str, Any]]: ...
    def normalize_result(self, result: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...
    def should_queue_next_page(self, payload: Any, results: list[dict[str, Any]], page: int, max_pages: int) -> bool: ...
