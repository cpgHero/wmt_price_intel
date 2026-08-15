from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from rci_locations import InMemoryLocationRepository, LocationImporter, RetailerCatalog
from rci_locations.importer import EXPECTED_COLUMNS, read_rows, transform_row
from rci_locations.models import LocationRecord
from rci_locations.normalization import normalize_zipcode

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPOSITORY_ROOT / "config" / "retailer-catalog.json"
LOCATION_SOURCE = REPOSITORY_ROOT / "fixtures" / "location_master" / "locations.csv"


class CountingRepository(InMemoryLocationRepository):
    def __init__(self) -> None:
        super().__init__()
        self.retailer_counts: Counter[str] = Counter()
        self.kroger_store_numbers: list[str] = []

    async def upsert_locations(self, import_id: str, locations: Sequence[LocationRecord]) -> None:
        del import_id
        self.retailer_counts.update(location.retailer_id for location in locations)
        self.kroger_store_numbers.extend(
            location.store_number
            for location in locations
            if location.retailer_id == "kroger_us" and location.store_number.startswith("0")
        )


def _write_source(path: Path, rows: list[dict[str, str]]) -> None:
    columns = sorted(EXPECTED_COLUMNS)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in EXPECTED_COLUMNS}
    row.update(
        {
            "id": "source-1",
            "Store_No": "00042",
            "Name": "Example Store",
            "Zip_Code": "5804",
            "Provider": "Walmart",
            "Status": "active",
            "Country": "USA",
            "mc_location_id": "000099",
        }
    )
    row.update(overrides)
    return row


def test_leading_zero_zip_and_raw_value_are_both_preserved() -> None:
    assert normalize_zipcode("5804", "USA") == "05804"
    location, _ = transform_row(_row(), RetailerCatalog.from_path(CATALOG_PATH))
    assert location.raw_zipcode == "5804"
    assert location.zipcode == "05804"


def test_target_australia_is_not_resolved_as_target_us() -> None:
    location, _ = transform_row(
        _row(Provider="Target", Country="Australia", Store_No="5213", Zip_Code="870"),
        RetailerCatalog.from_path(CATALOG_PATH),
    )
    assert location.retailer_id == "target__au"
    assert location.retailer_id != "target_us"
    assert location.country == "AUSTRALIA"
    assert location.zipcode == "870"


def test_api_aliases_resolve_within_country() -> None:
    catalog = RetailerCatalog.from_path(CATALOG_PATH)
    assert catalog.resolve("new_aldi", "USA").retailer.id == "aldi_us"
    assert catalog.resolve("ALDI.US", "US").retailer.id == "aldi_us"
    assert catalog.resolve("gianteagle.com", "USA").retailer.id == "giant_eagle_us"
    assert catalog.resolve("Trader Joe's", "US").retailer.id == "trader_joes_us"
    assert catalog.resolve("Target", "Australia").retailer.id == "target__au"


async def test_reimport_is_idempotent_and_identifiers_remain_strings(tmp_path: Path) -> None:
    source = tmp_path / "locations.csv"
    _write_source(
        source,
        [
            _row(),
            _row(
                id="source-2",
                Provider="kroger",
                Store_No="03500995",
                Zip_Code="75241",
                mc_location_id="00019369",
            ),
        ],
    )
    repository = InMemoryLocationRepository()
    importer = LocationImporter(repository, RetailerCatalog.from_path(CATALOG_PATH), batch_size=1)

    first = await importer.import_file(source)
    second = await importer.import_file(source)

    assert first.imported_rows == second.imported_rows == 2
    assert len(repository.locations) == 2
    kroger = next(
        location
        for location in repository.locations.values()
        if location.retailer_id == "kroger_us"
    )
    assert kroger.store_number == "03500995"
    assert kroger.provider_location_id == "00019369"
    assert kroger.raw_row["Store_No"] == "03500995"
    assert len(repository.imports) == 2
    assert all(state.status == "completed" for state in repository.imports.values())


async def test_complete_supplied_location_master_is_country_scoped() -> None:
    repository = CountingRepository()
    importer = LocationImporter(
        repository,
        RetailerCatalog.from_path(CATALOG_PATH),
        batch_size=5_000,
    )

    summary = await importer.import_file(LOCATION_SOURCE)

    assert summary.total_rows == 157806
    assert summary.imported_rows == 157806
    assert summary.skipped_rows == 0
    assert repository.retailer_counts["walmart_us"] == 4683
    assert repository.retailer_counts["aldi_us"] == 2627
    assert repository.retailer_counts["target_us"] == 2023
    assert repository.retailer_counts["target__au"] == 124
    assert repository.retailer_counts["target__unknown"] == 1
    assert "03500995" in repository.kroger_store_numbers


def test_source_reader_preserves_raw_identifier_text() -> None:
    kroger_row = next(
        row
        for row in read_rows(LOCATION_SOURCE)
        if row["Provider"] == "kroger" and row["Store_No"].startswith("0")
    )
    assert kroger_row["Store_No"] == "03500995"
