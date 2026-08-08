"""Retailer catalog resolution scoped by provider and country."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rci_locations.models import ResolvedRetailer, RetailerAlias, RetailerDefinition
from rci_locations.normalization import (
    country_id_suffix,
    normalize_alias,
    normalize_country,
    slugify,
)


def _catalog_country(retailer_id: str) -> str:
    parts = set(retailer_id.split("_"))
    if "us" in parts:
        return "USA"
    if "mx" in parts:
        return "MEXICO"
    if "pr" in parts:
        return "PR"
    return "UNKNOWN"


class RetailerCatalog:
    """Resolve a raw provider/country pair without cross-country alias leakage."""

    def __init__(self, catalog: dict[str, Any]) -> None:
        self._known: dict[tuple[str, str], ResolvedRetailer] = {}
        self._static: dict[str, ResolvedRetailer] = {}
        self._dynamic: dict[tuple[str, str], ResolvedRetailer] = {}
        for item in catalog.get("retailers", []):
            resolved = self._from_catalog_item(item)
            self._static[resolved.retailer.id] = resolved
            for alias in resolved.aliases:
                self._known[(alias.alias, resolved.retailer.country)] = resolved

    @classmethod
    def from_path(cls, path: Path) -> RetailerCatalog:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def _from_catalog_item(self, item: dict[str, Any]) -> ResolvedRetailer:
        retailer_id = str(item["id"])
        country = _catalog_country(retailer_id)
        status = str(item.get("status", "catalogued"))
        retailer = RetailerDefinition(
            id=retailer_id,
            display_name=str(item["display_name"]),
            country=country,
            active=status == "enabled",
            catalogued=True,
        )
        raw_aliases = {
            retailer_id,
            str(item["display_name"]),
            *(str(alias) for alias in item.get("api_retailer_aliases", [])),
        }
        location_provider = item.get("location_provider")
        if location_provider is not None:
            raw_aliases.add(str(location_provider))
        normalized_aliases = {normalize_alias(value) for value in raw_aliases}
        aliases = tuple(
            RetailerAlias(alias=alias, country=country, retailer_id=retailer_id)
            for alias in sorted(value for value in normalized_aliases if value is not None)
        )
        return ResolvedRetailer(retailer=retailer, aliases=aliases)

    def resolve(self, provider: str, country: str) -> ResolvedRetailer:
        normalized_provider = normalize_alias(provider)
        if normalized_provider is None:
            raise ValueError("provider is required")
        canonical_country = normalize_country(country)
        known = self._known.get((normalized_provider, canonical_country))
        if known is not None:
            return known

        key = (normalized_provider, canonical_country)
        cached = self._dynamic.get(key)
        if cached is not None:
            return cached

        retailer_id = f"{slugify(provider)}__{country_id_suffix(canonical_country)}"
        display_country = canonical_country.title() if canonical_country != "UNKNOWN" else "Unknown"
        retailer = RetailerDefinition(
            id=retailer_id,
            display_name=f"{provider.strip()} ({display_country})",
            country=canonical_country,
            active=False,
            catalogued=False,
        )
        aliases = (
            RetailerAlias(
                alias=normalized_provider,
                country=canonical_country,
                retailer_id=retailer_id,
            ),
        )
        resolved = ResolvedRetailer(retailer=retailer, aliases=aliases)
        self._dynamic[key] = resolved
        return resolved

    def static_retailers(self) -> tuple[ResolvedRetailer, ...]:
        return tuple(self._static[key] for key in sorted(self._static))
