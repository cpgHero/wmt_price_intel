"""Configuration-driven first-party seller admission for marketplace retailers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rci_retailer_packs.catalog import FileRetailerPackCatalog, JsonObject, RetailerPack

SellerStatus = Literal[
    "verified_first_party",
    "seller_unverified",
    "excluded_third_party",
    "not_governed",
]


def normalize_seller_name(value: str) -> str:
    """Normalize seller display names without broad or substring matching."""

    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_value)).strip("_")


@dataclass(frozen=True, slots=True)
class SellerResolution:
    retailer_id: str
    observed_seller: str | None
    normalized_seller: str
    status: SellerStatus
    eligible: bool
    resolution_method: Literal[
        "exact_allowed_seller",
        "missing_allowed",
        "exact_non_first_party",
        "policy_not_configured",
        "allow_all",
    ]
    retailer_pack_version: str | None
    retailer_pack_checksum: str | None

    def to_record(self) -> JsonObject:
        return {
            "retailer_id": self.retailer_id,
            "observed_seller": self.observed_seller,
            "normalized_seller": self.normalized_seller,
            "status": self.status,
            "eligible": self.eligible,
            "resolution_method": self.resolution_method,
            "source": "pdp_seller",
            "retailer_pack": (
                {
                    "version": self.retailer_pack_version,
                    "checksum_sha256": self.retailer_pack_checksum,
                }
                if self.retailer_pack_version and self.retailer_pack_checksum
                else None
            ),
        }


class GovernedSellerResolver:
    """Apply Retailer Pack seller rules without retailer branches in core code."""

    def __init__(self, packs: dict[str, RetailerPack]) -> None:
        self._packs = dict(packs)

    @classmethod
    def from_repository(
        cls,
        repository_root: Path,
        retailer_versions: dict[str, str] | None = None,
    ) -> GovernedSellerResolver:
        catalog = FileRetailerPackCatalog(repository_root)
        packs = (
            catalog.active_versions()
            if retailer_versions is None
            else {
                retailer_id: catalog.get(retailer_id, version)
                for retailer_id, version in retailer_versions.items()
            }
        )
        return cls(packs)

    def resolve(self, retailer_id: str, observed_seller: str | None) -> SellerResolution:
        pack = self._packs.get(retailer_id)
        observed = str(observed_seller).strip() if observed_seller is not None else ""
        normalized = normalize_seller_name(observed)
        if pack is None or not isinstance(pack.document.get("seller_policy"), dict):
            return SellerResolution(
                retailer_id=retailer_id,
                observed_seller=observed or None,
                normalized_seller=normalized,
                status="not_governed",
                eligible=True,
                resolution_method="policy_not_configured",
                retailer_pack_version=pack.version if pack else None,
                retailer_pack_checksum=pack.checksum if pack else None,
            )
        policy = pack.document["seller_policy"]
        if str(policy["mode"]) == "allow_all":
            return SellerResolution(
                retailer_id=retailer_id,
                observed_seller=observed or None,
                normalized_seller=normalized,
                status="not_governed",
                eligible=True,
                resolution_method="allow_all",
                retailer_pack_version=pack.version,
                retailer_pack_checksum=pack.checksum,
            )
        if not normalized:
            allowed = bool(policy["allow_when_missing"])
            return SellerResolution(
                retailer_id=retailer_id,
                observed_seller=None,
                normalized_seller="",
                status="seller_unverified" if allowed else "excluded_third_party",
                eligible=allowed,
                resolution_method="missing_allowed" if allowed else "exact_non_first_party",
                retailer_pack_version=pack.version,
                retailer_pack_checksum=pack.checksum,
            )
        allowed_names = {
            normalize_seller_name(str(value)) for value in policy["allowed_first_party_sellers"]
        }
        eligible = normalized in allowed_names
        return SellerResolution(
            retailer_id=retailer_id,
            observed_seller=observed,
            normalized_seller=normalized,
            status="verified_first_party" if eligible else "excluded_third_party",
            eligible=eligible,
            resolution_method=("exact_allowed_seller" if eligible else "exact_non_first_party"),
            retailer_pack_version=pack.version,
            retailer_pack_checksum=pack.checksum,
        )
