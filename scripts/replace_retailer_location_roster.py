#!/usr/bin/env python3
"""Replace one retailer/country slice in the canonical location fixture."""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from pathlib import Path


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace an authoritative retailer slice in a canonical location CSV."
    )
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--country", required=True)
    args = parser.parse_args()

    master_columns, master_rows = read_rows(args.master)
    source_columns, source_rows = read_rows(args.source)
    required = {
        "Store_No",
        "Name",
        "Latitude",
        "Longitude",
        "Address",
        "Street",
        "City",
        "State",
        "Zip_Code",
        "Provider",
        "Status",
        "Country",
        "mc_location_id",
    }
    missing = required - set(source_columns)
    if missing:
        raise SystemExit(f"source is missing required columns: {sorted(missing)}")
    if not source_rows:
        raise SystemExit("source contains no rows")
    if {row["Provider"] for row in source_rows} != {args.provider}:
        raise SystemExit("source contains an unexpected provider")
    if {row["Country"] for row in source_rows} != {args.country}:
        raise SystemExit("source contains an unexpected country")
    store_numbers = [row["Store_No"] for row in source_rows]
    if len(store_numbers) != len(set(store_numbers)):
        raise SystemExit("source contains duplicate Store_No values")

    matching_indexes = [
        index
        for index, row in enumerate(master_rows)
        if row["Provider"] == args.provider and row["Country"] == args.country
    ]
    if not matching_indexes:
        raise SystemExit("master contains no matching retailer slice")
    insert_at = matching_indexes[0]
    retained = [
        row
        for row in master_rows
        if not (row["Provider"] == args.provider and row["Country"] == args.country)
    ]
    normalized_source = [
        {column: row.get(column, "") for column in master_columns} for row in source_rows
    ]
    replacement = retained[:insert_at] + normalized_source + retained[insert_at:]

    args.master.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{args.master.name}.", suffix=".tmp", dir=args.master.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=master_columns,
                lineterminator="\n",
                quoting=csv.QUOTE_ALL,
            )
            writer.writeheader()
            writer.writerows(replacement)
        os.replace(temporary_name, args.master)
    except Exception:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise

    print(
        f"replaced {len(matching_indexes)} {args.provider}/{args.country} rows "
        f"with {len(source_rows)} rows; canonical total={len(replacement)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
