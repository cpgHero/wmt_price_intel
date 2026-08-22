"""Streaming, idempotent location-master import orchestration."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from pathlib import Path

from rci_locations.catalog import RetailerCatalog
from rci_locations.models import ImportSummary, LocationRecord, ResolvedRetailer
from rci_locations.normalization import (
    normalize_country,
    normalize_identifier,
    normalize_zipcode,
    parse_coordinate,
)
from rci_locations.ports import LocationRepository

EXPECTED_COLUMNS = {
    "id",
    "created_at",
    "Store_No",
    "Name",
    "Latitude",
    "Longitude",
    "Address",
    "Street",
    "City",
    "State",
    "Zip_Code",
    "County",
    "Phone",
    "Provider",
    "Status",
    "Country",
    "mc_location_id",
}


def source_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _required(row: dict[str, str], key: str) -> str:
    value = normalize_identifier(row.get(key))
    if value is None:
        raise ValueError(f"location row requires {key}")
    return value


def transform_row(
    row: dict[str, str], catalog: RetailerCatalog
) -> tuple[LocationRecord, ResolvedRetailer]:
    provider = _required(row, "Provider")
    store_number = _required(row, "Store_No")
    country = normalize_country(row.get("Country"))
    resolved = catalog.resolve(provider, country)
    raw_zipcode = normalize_identifier(row.get("Zip_Code"))
    status = normalize_identifier(row.get("Status"))
    collection_eligible, collection_eligibility_reason = catalog.collection_eligibility(
        resolved,
        store_number=store_number,
        status=status,
    )
    record = LocationRecord(
        retailer_id=resolved.retailer.id,
        provider=provider,
        provider_location_id=normalize_identifier(row.get("mc_location_id")),
        store_number=store_number,
        store_name=normalize_identifier(row.get("Name")),
        raw_zipcode=raw_zipcode,
        zipcode=normalize_zipcode(raw_zipcode, country),
        street=normalize_identifier(row.get("Street")),
        address=normalize_identifier(row.get("Address")),
        city=normalize_identifier(row.get("City")),
        state=normalize_identifier(row.get("State")),
        county=normalize_identifier(row.get("County")),
        country=country,
        latitude=parse_coordinate(row.get("Latitude")),
        longitude=parse_coordinate(row.get("Longitude")),
        status=status,
        collection_eligible=collection_eligible,
        collection_eligibility_reason=collection_eligibility_reason,
        source_created_at=normalize_identifier(row.get("created_at")),
        source_row_id=normalize_identifier(row.get("id")),
        raw_row=dict(row),
    )
    return record, resolved


def read_rows(source: Path) -> Iterator[dict[str, str]]:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = EXPECTED_COLUMNS - columns
        if missing:
            raise ValueError(f"location source is missing columns: {sorted(missing)}")
        for row in reader:
            yield {key: value or "" for key, value in row.items() if key is not None}


class LocationImporter:
    def __init__(
        self,
        repository: LocationRepository,
        catalog: RetailerCatalog,
        *,
        batch_size: int = 1_000,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._repository = repository
        self._catalog = catalog
        self._batch_size = batch_size

    async def import_file(self, source: Path) -> ImportSummary:
        resolved_source = source.resolve()
        checksum = source_sha256(resolved_source)
        import_id = await self._repository.begin_import(str(resolved_source), checksum)
        total_rows = 0
        imported_rows = 0
        skipped_rows = 0
        seeded_retailers: set[str] = set()
        batch: list[LocationRecord] = []

        try:
            for row in read_rows(resolved_source):
                total_rows += 1
                try:
                    location, resolved = transform_row(row, self._catalog)
                except (TypeError, ValueError):
                    skipped_rows += 1
                    continue

                if resolved.retailer.id not in seeded_retailers:
                    await self._repository.upsert_retailers(
                        [resolved.retailer], list(resolved.aliases)
                    )
                    seeded_retailers.add(resolved.retailer.id)
                batch.append(location)
                if len(batch) >= self._batch_size:
                    await self._repository.upsert_locations(import_id, batch)
                    imported_rows += len(batch)
                    batch = []
                    await self._repository.update_import_progress(
                        import_id,
                        total_rows=total_rows,
                        imported_rows=imported_rows,
                        skipped_rows=skipped_rows,
                        retailer_count=len(seeded_retailers),
                    )

            if batch:
                await self._repository.upsert_locations(import_id, batch)
                imported_rows += len(batch)

            await self._repository.update_import_progress(
                import_id,
                total_rows=total_rows,
                imported_rows=imported_rows,
                skipped_rows=skipped_rows,
                retailer_count=len(seeded_retailers),
            )

            for static in self._catalog.static_retailers():
                if static.retailer.id not in seeded_retailers:
                    await self._repository.upsert_retailers([static.retailer], list(static.aliases))
                    seeded_retailers.add(static.retailer.id)

            summary = ImportSummary(
                import_id=import_id,
                source_path=str(resolved_source),
                source_sha256=checksum,
                total_rows=total_rows,
                imported_rows=imported_rows,
                skipped_rows=skipped_rows,
                retailer_count=len(seeded_retailers),
            )
            await self._repository.complete_import(summary)
            return summary
        except Exception as exc:
            await self._repository.fail_import(import_id, str(exc))
            raise
