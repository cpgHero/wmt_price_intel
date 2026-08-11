"""MetricsCart collection capabilities sourced from the retailer catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rci_collections.models import RetailerCapability


class CollectionRetailerCatalog:
    def __init__(self, catalog: dict[str, Any]) -> None:
        self._retailers = {
            str(item["id"]): RetailerCapability(
                retailer_id=str(item["id"]),
                display_name=str(item["display_name"]),
                adapter_id=str(item.get("adapter_id", "")),
                status=str(item.get("status", "catalogued")),
                location_dimension=str(item["location_dimension"]),
                credits_per_successful_page=int(item["credits_per_successful_page"]),
                endpoint=str(item["endpoint"]),
            )
            for item in catalog.get("retailers", [])
        }

    @classmethod
    def from_path(cls, path: Path) -> CollectionRetailerCatalog:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def get(self, retailer_id: str) -> RetailerCapability:
        try:
            return self._retailers[retailer_id]
        except KeyError as exc:
            raise ValueError(
                f"retailer {retailer_id!r} is absent from the retailer catalog"
            ) from exc

    def enabled(self) -> tuple[RetailerCapability, ...]:
        return tuple(
            sorted(
                (item for item in self._retailers.values() if item.status == "enabled"),
                key=lambda item: (item.display_name, item.retailer_id),
            )
        )
