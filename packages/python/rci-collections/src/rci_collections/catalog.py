"""MetricsCart collection capabilities sourced from the retailer catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rci_collections.models import RetailerCapability
from rci_collections.request_contract import provider_request_contract_from_catalog_item


class CollectionRetailerCatalog:
    def __init__(self, catalog: dict[str, Any]) -> None:
        self._provider_error_evidence_contracts = {
            str(item["adapter_id"]): dict(item["provider_error_evidence_contract"])
            for item in catalog.get("retailers", [])
            if item.get("adapter_id")
            and isinstance(item.get("provider_error_evidence_contract"), dict)
        }
        self._retailers = {
            str(item["id"]): RetailerCapability(
                retailer_id=str(item["id"]),
                display_name=str(item["display_name"]),
                adapter_id=str(item.get("adapter_id", "")),
                status=str(item.get("status", "catalogued")),
                location_dimension=str(item["location_dimension"]),
                credits_per_successful_page=int(item["credits_per_successful_page"]),
                endpoint=str(item["endpoint"]),
                supports_pagination="page" in item.get("supported_params", []),
                provider_request_contract=(
                    provider_request_contract_from_catalog_item(item)
                    if item.get("adapter_id")
                    else {}
                ),
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

    def provider_request_contracts(self) -> dict[str, dict[str, Any]]:
        """Return immutable request contracts keyed by adapter id."""

        return {
            item.adapter_id: dict(item.provider_request_contract)
            for item in self._retailers.values()
            if item.adapter_id and item.provider_request_contract
        }

    def provider_error_evidence_contracts(self) -> dict[str, dict[str, Any]]:
        """Return reviewed response-body evidence contracts keyed by adapter id."""

        return {
            adapter_id: dict(contract)
            for adapter_id, contract in self._provider_error_evidence_contracts.items()
        }
