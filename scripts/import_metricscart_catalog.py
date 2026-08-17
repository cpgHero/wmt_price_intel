#!/usr/bin/env python3
"""Normalize an owner-supplied MetricsCart catalog without copying sample payloads.

The provider export contains large response examples and request placeholders. This importer
keeps the endpoint contract, field inventory, and cryptographic provenance needed for review
while ensuring the repository never becomes a second store for provider response bodies.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

EXPORT_PREFIX = "metricscart-catalog-export/"
EXPECTED_FILES = (
    "README.md",
    "endpoints-flat.json",
    "endpoints.csv",
    "playground-api-catalog.json",
    "raw-api_endpoint.json",
    "raw-api_endpoint_parameter.json",
    "raw-data_source.json",
)

PDP_RETAILERS = {
    "albertsons": "albertsons_us",
    "new_aldi": "aldi_us",
    "shop_aldi": "aldi_instacart_us",
    "amazon": "amazon_us_same_day",
    "gianteagle": "giant_eagle_us",
    "heb": "heb_us",
    "kroger": "kroger_us",
    "meijer": "meijer_us",
    "safeway": "safeway_us",
    "samsclub": "sams_club_us",
    "shoprite": "shoprite_us",
    "target": "target_us",
    "traderjoes": "trader_joes_us",
    "walmart": "walmart_us",
    "walmart_mx": "walmart_mx",
    "wegmans": "wegmans_us",
}

PDP_ENDPOINT_IDS = {
    "albertsons": "11",
    "new_aldi": "14",
    "shop_aldi": "16",
    "amazon": "41",
    "gianteagle": "88",
    "heb": "93",
    "kroger": "105",
    "meijer": "116",
    "safeway": "151",
    "samsclub": "155",
    "shoprite": "162",
    "target": "172",
    "traderjoes": "178",
    "walmart": "3",
    "walmart_mx": "189",
    "wegmans": "194",
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def _without_auth(parameters: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in parameters if str(row.get("name")) != "x-api-key"]


def _normalized_endpoint(row: dict[str, object]) -> dict[str, object]:
    parameters = _without_auth(list(row["parameters"]))
    sample = row.get("sample_response")
    sample_fields = sorted(str(key) for key in sample) if isinstance(sample, dict) else []
    return {
        "retailer_name": str(row["retailer_name"]),
        "provider_retailer": str(row["retailer_provider"]),
        "domain": str(row["retailer_domain"]),
        "endpoint_id": str(row["endpoint_id"]),
        "name": str(row["name"]),
        "method": str(row["method"]),
        "path": str(row["endpoint_path"]),
        "credits": int(row["credits"]),
        "active": bool(row["is_active"]),
        "required_params": [
            str(parameter["name"]) for parameter in parameters if parameter["is_required"]
        ],
        "supported_params": [str(parameter["name"]) for parameter in parameters],
        "parameter_defaults": {
            str(parameter["name"]): str(parameter["default_value"])
            for parameter in parameters
            if str(parameter.get("default_value") or "").strip()
        },
        "sample_response": {
            "present": sample is not None,
            "json_type": type(sample).__name__ if sample is not None else None,
            "sha256": _sha256(_canonical(sample)) if sample is not None else None,
            "top_level_fields": sample_fields,
        },
    }


def main() -> None:
    args = _arguments()
    archive = args.archive.resolve(strict=True)
    root = args.repository_root.resolve(strict=True)
    archive_bytes = archive.read_bytes()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as source:
        corrupt = source.testzip()
        if corrupt is not None:
            raise ValueError(f"catalog archive failed CRC validation at {corrupt}")
        names = {name.removeprefix(EXPORT_PREFIX) for name in source.namelist() if name != EXPORT_PREFIX}
        missing = sorted(set(EXPECTED_FILES) - names)
        if missing:
            raise ValueError(f"catalog archive is missing: {', '.join(missing)}")
        raw_endpoints = json.loads(source.read(f"{EXPORT_PREFIX}endpoints-flat.json"))
        playground = json.loads(source.read(f"{EXPORT_PREFIX}playground-api-catalog.json"))
        entries = {
            name: {
                "byte_size": source.getinfo(f"{EXPORT_PREFIX}{name}").file_size,
                "sha256": _sha256(source.read(f"{EXPORT_PREFIX}{name}")),
            }
            for name in EXPECTED_FILES
        }

    endpoints = [_normalized_endpoint(dict(row)) for row in raw_endpoints]
    normalized = {
        "schema_version": "1.0.0",
        "catalog_version": "2026-08-16",
        "provider": "metricscart",
        "generated_at": playground["generated_at"],
        "base_url": playground["base_url"],
        "source_archive": {
            "filename": archive.name,
            "byte_size": len(archive_bytes),
            "sha256": _sha256(archive_bytes),
        },
        "counts": {
            "retailers": int(playground["counts"]["retailers"]),
            "endpoints": len(endpoints),
            "active_endpoints": sum(bool(endpoint["active"]) for endpoint in endpoints),
            "endpoints_with_sample_response": sum(
                bool(endpoint["sample_response"]["present"]) for endpoint in endpoints
            ),
        },
        "endpoints": endpoints,
    }
    manifest = {
        "schema_version": "1.0.0",
        "catalog_version": "2026-08-16",
        "source_archive": normalized["source_archive"],
        "archive_crc_valid": True,
        "files": entries,
        "notes": [
            "The source archive remains owner-supplied and is not committed.",
            "The normalized catalog stores sample hashes and field inventories, not response bodies.",
            "No provider credential is present; the export uses the MY_API_KEY placeholder.",
        ],
    }
    output = root / "config" / "metricscart-api-catalog-20260816.json"
    output.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_path = root / "source_material" / "metricscart-api-catalog-20260816.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    endpoint_by_key = {
        (str(endpoint["provider_retailer"]), str(endpoint["endpoint_id"])): endpoint
        for endpoint in endpoints
    }
    csv_path = (
        root
        / "source_material"
        / "metricscart_product_details_by_zipcode_apis_20260816.csv"
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "retailer_id",
                "provider",
                "domain",
                "endpoint_id",
                "method",
                "inferred_metricscart_path",
                "credits",
                "required_params",
                "all_params",
                "sample_response_sha256",
            ),
        )
        writer.writeheader()
        for provider, retailer_id in PDP_RETAILERS.items():
            endpoint = endpoint_by_key[(provider, PDP_ENDPOINT_IDS[provider])]
            writer.writerow(
                {
                    "retailer_id": retailer_id,
                    "provider": provider,
                    "domain": endpoint["domain"],
                    "endpoint_id": endpoint["endpoint_id"],
                    "method": endpoint["method"],
                    "inferred_metricscart_path": endpoint["path"],
                    "credits": endpoint["credits"],
                    "required_params": "|".join(endpoint["required_params"]),
                    "all_params": "|".join(endpoint["supported_params"]),
                    "sample_response_sha256": endpoint["sample_response"]["sha256"],
                }
            )

    print(
        json.dumps(
            {
                "catalog": str(output),
                "manifest": str(manifest_path),
                "pdp_catalog": str(csv_path),
                "endpoints": len(endpoints),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
