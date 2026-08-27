"""Location-master administration CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from rci_core import AppSettings
from rci_db import DatabaseProbe
from rci_locations.catalog import RetailerCatalog
from rci_locations.importer import LocationImporter
from rci_locations.repository import PostgresLocationRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import the RCI location master into Postgres.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("fixtures/location_master/locations.csv"),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("config/retailer-catalog.json"),
    )
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument(
        "--authoritative-retailer",
        action="append",
        default=[],
        help=(
            "Retailer ID whose existing locations absent from this import should be retained "
            "for audit but marked superseded and collection-ineligible. Repeat as needed."
        ),
    )
    return parser


async def run_import(
    source: Path,
    catalog_path: Path,
    batch_size: int,
    authoritative_retailers: set[str] | None = None,
) -> int:
    database = DatabaseProbe(AppSettings.from_env().database_url)
    try:
        repository = PostgresLocationRepository(database.engine)
        catalog = RetailerCatalog.from_path(catalog_path.resolve())
        summary = await LocationImporter(repository, catalog, batch_size=batch_size).import_file(
            source,
            authoritative_retailer_ids=authoritative_retailers,
        )
        print(json.dumps(asdict(summary), indent=2, sort_keys=True))
    finally:
        await database.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(
        run_import(
            args.source,
            args.catalog,
            args.batch_size,
            set(args.authoritative_retailer),
        )
    )
