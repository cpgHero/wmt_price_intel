"""Typed records crossing location-master boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RetailerDefinition:
    id: str
    display_name: str
    country: str
    active: bool
    catalogued: bool


@dataclass(frozen=True, slots=True)
class RetailerAlias:
    alias: str
    country: str
    retailer_id: str


@dataclass(frozen=True, slots=True)
class ResolvedRetailer:
    retailer: RetailerDefinition
    aliases: tuple[RetailerAlias, ...]


@dataclass(frozen=True, slots=True)
class LocationCollectionPolicy:
    eligible_statuses: frozenset[str]
    store_number_pattern: str


@dataclass(frozen=True, slots=True)
class LocationRecord:
    retailer_id: str
    provider: str
    provider_location_id: str | None
    store_number: str
    store_name: str | None
    raw_zipcode: str | None
    zipcode: str | None
    street: str | None
    address: str | None
    city: str | None
    state: str | None
    county: str | None
    country: str
    latitude: float | None
    longitude: float | None
    status: str | None
    collection_eligible: bool
    collection_eligibility_reason: str | None
    source_created_at: str | None
    source_row_id: str | None
    raw_row: dict[str, str]

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return self.retailer_id, self.provider, self.store_number, self.country


@dataclass(frozen=True, slots=True)
class ImportSummary:
    import_id: str
    source_path: str
    source_sha256: str
    total_rows: int
    imported_rows: int
    skipped_rows: int
    retailer_count: int


@dataclass(frozen=True, slots=True)
class RetailerCount:
    id: str
    display_name: str
    country: str
    active: bool
    catalogued: bool
    location_count: int


@dataclass(frozen=True, slots=True)
class LocationSearchResult:
    id: str
    retailer_id: str
    provider: str
    provider_location_id: str | None
    store_number: str
    store_name: str | None
    raw_zipcode: str | None
    zipcode: str | None
    city: str | None
    state: str | None
    country: str
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True, slots=True)
class ImportState:
    id: str
    source_path: str
    source_sha256: str
    status: str
    total_rows: int
    imported_rows: int
    skipped_rows: int
    retailer_count: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


JsonObject = dict[str, Any]
