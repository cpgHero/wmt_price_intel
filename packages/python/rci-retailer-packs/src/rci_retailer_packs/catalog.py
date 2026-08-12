"""Immutable Retailer Pack and brand-foundation loading and resolution."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from rci_contracts import ContractError, validate_instance

JsonObject = dict[str, Any]
BrandRole = Literal["private_label", "regional", "national", "unclassified"]


def canonical_checksum(document: JsonObject) -> str:
    body = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(body).hexdigest()


def normalize_brand_name(value: str) -> str:
    """Produce the stable key used by the supplied brand foundation.

    Apostrophes are removed instead of becoming word separators so ``Sam's`` and
    ``Sams`` resolve identically. Ampersands normalize to ``and``. The raw value is
    always retained separately in source data and discovery records.
    """

    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii").casefold()
    normalized = ascii_value.replace("&", " and ")
    normalized = normalized.replace("'", "").replace("\N{RIGHT SINGLE QUOTATION MARK}", "")
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", normalized)).strip("_")


@dataclass(frozen=True, slots=True)
class RetailerPack:
    id: str
    display_name: str
    version: str
    checksum: str
    document: JsonObject


@dataclass(frozen=True, slots=True)
class BrandFoundation:
    id: str
    name: str
    version: str
    checksum: str
    document: JsonObject


@dataclass(frozen=True, slots=True)
class BrandResolution:
    retailer_id: str
    observed_brand: str
    normalized_brand: str
    status: Literal["resolved", "unresolved"]
    resolution_method: Literal[
        "exact_canonical", "exact_alias", "legacy_alias", "governed_override", "unresolved"
    ]
    canonical_brand_id: str | None
    canonical_brand_name: str | None
    role: BrandRole
    strict_private_label: bool
    brand_bucket: str | None
    brand_class: str | None
    ownership_model: str | None
    competitive_brand_role: str | None
    review_status: str | None
    temporal_status: str | None
    confidence: str | None
    matching_priority: str | None
    foundation_id: str
    foundation_version: str
    foundation_checksum: str
    override_decision: str | None = None

    def to_record(self) -> JsonObject:
        return {
            "retailer_id": self.retailer_id,
            "observed_brand": self.observed_brand,
            "normalized_brand": self.normalized_brand,
            "status": self.status,
            "resolution_method": self.resolution_method,
            "canonical_brand_id": self.canonical_brand_id,
            "canonical_brand_name": self.canonical_brand_name,
            "role": self.role,
            "strict_private_label": self.strict_private_label,
            "brand_bucket": self.brand_bucket,
            "brand_class": self.brand_class,
            "ownership_model": self.ownership_model,
            "competitive_brand_role": self.competitive_brand_role,
            "review_status": self.review_status,
            "temporal_status": self.temporal_status,
            "confidence": self.confidence,
            "matching_priority": self.matching_priority,
            "foundation": {
                "id": self.foundation_id,
                "version": self.foundation_version,
                "checksum_sha256": self.foundation_checksum,
            },
            "override_decision": self.override_decision,
        }


@dataclass(frozen=True, slots=True)
class BrandDecisionOverride:
    retailer_id: str
    normalized_brand: str
    display_brand: str
    role: BrandRole
    decision: Literal["confirmed", "rejected"]


class FileRetailerPackCatalog:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def versions(self) -> tuple[RetailerPack, ...]:
        index_path = self._root / "retailer-packs" / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        records: list[RetailerPack] = []
        seen: set[tuple[str, str]] = set()
        retailer_catalog = json.loads(
            (self._root / "config" / "retailer-catalog.json").read_text(encoding="utf-8")
        )
        catalog_ids = {
            str(row["id"])
            for group in ("retailers", "normalization_only_retailers")
            for row in retailer_catalog.get(group, [])
        }
        for summary in index["packs"]:
            path = self._root / "retailer-packs" / str(summary["file"])
            document = json.loads(path.read_text(encoding="utf-8"))
            validate_instance(self._root, "retailer-pack.schema.json", document, label=str(path))
            key = (str(document["id"]), str(document["version"]))
            if key in seen:
                raise ContractError(f"duplicate Retailer Pack version {key[0]}@{key[1]}")
            if key != (str(summary["id"]), str(summary["version"])):
                raise ContractError(f"Retailer Pack index does not match {path}")
            if key[0] not in catalog_ids:
                raise ContractError(f"Retailer Pack {key[0]!r} is absent from retailer catalog")
            if str(document["identity"]["canonical_retailer_id"]) != key[0]:
                raise ContractError(f"Retailer Pack {key[0]!r} has mismatched canonical identity")
            seen.add(key)
            records.append(
                RetailerPack(
                    id=key[0],
                    display_name=str(document["display_name"]),
                    version=key[1],
                    checksum=canonical_checksum(document),
                    document=document,
                )
            )
        return tuple(records)

    def get(self, retailer_id: str, version: str) -> RetailerPack:
        try:
            return next(
                record
                for record in self.versions()
                if (record.id, record.version) == (retailer_id, version)
            )
        except StopIteration as exc:
            raise LookupError(f"Retailer Pack {retailer_id}@{version} was not found") from exc

    def active_versions(self) -> dict[str, RetailerPack]:
        return {record.id: record for record in self.versions()}


class BrandFoundationLoader:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def load(self, foundation_id: str, version: str) -> BrandFoundation:
        index_path = self._root / "brand-foundations" / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        try:
            summary = next(
                row
                for row in index["foundations"]
                if (str(row["id"]), str(row["version"])) == (foundation_id, version)
            )
        except StopIteration as exc:
            raise LookupError(f"Brand foundation {foundation_id}@{version} was not found") from exc
        path = self._root / "brand-foundations" / str(summary["file"])
        document = json.loads(path.read_text(encoding="utf-8"))
        validate_instance(self._root, "brand-foundation.schema.json", document, label=str(path))
        self._validate_semantics(document)
        return BrandFoundation(
            id=str(document["id"]),
            name=str(document["name"]),
            version=str(document["version"]),
            checksum=canonical_checksum(document),
            document=document,
        )

    @staticmethod
    def _validate_semantics(document: JsonObject) -> None:
        brand_ids: set[str] = set()
        retailer_names: set[tuple[str, str]] = set()
        retailer_by_brand: dict[str, str] = {}
        for brand in document["brands"]:
            brand_id = str(brand["brand_id"])
            key = (str(brand["retailer_id"]), str(brand["brand_name_normalized"]))
            if brand_id in brand_ids:
                raise ContractError(f"duplicate brand ID {brand_id!r}")
            if key in retailer_names:
                raise ContractError(f"duplicate canonical retailer brand {key!r}")
            brand_ids.add(brand_id)
            retailer_names.add(key)
            retailer_by_brand[brand_id] = str(brand["retailer_id"])
        alias_ids: set[str] = set()
        aliases: dict[tuple[str, str], str] = {}
        for alias in document["aliases"]:
            alias_id = str(alias["alias_id"])
            if alias_id in alias_ids:
                raise ContractError(f"duplicate alias ID {alias_id!r}")
            alias_ids.add(alias_id)
            canonical_brand_id = str(alias["canonical_brand_id"])
            retailer_id = str(alias["retailer_id"])
            if canonical_brand_id not in brand_ids:
                raise ContractError(f"alias references unknown brand {canonical_brand_id!r}")
            if retailer_by_brand[canonical_brand_id] != retailer_id:
                raise ContractError(f"alias crosses retailer context {alias_id!r}")
            key = (retailer_id, str(alias["alias_normalized"]))
            existing = aliases.get(key)
            if existing is not None and existing != canonical_brand_id:
                raise ContractError(f"ambiguous exact alias {key!r}")
            aliases[key] = canonical_brand_id


class GovernedBrandResolver:
    """Retailer-scoped exact brand resolver with conservative strict-PL eligibility."""

    def __init__(
        self,
        packs: dict[str, RetailerPack],
        foundation: BrandFoundation,
        *,
        overrides: dict[tuple[str, str], BrandDecisionOverride] | None = None,
    ) -> None:
        self._packs = dict(packs)
        self.foundation = foundation
        self._overrides = dict(overrides or {})
        self._brands_by_id = {
            str(row["brand_id"]): dict(row) for row in foundation.document["brands"]
        }
        self._canonical = {
            (str(row["retailer_id"]), str(row["brand_name_normalized"])): dict(row)
            for row in foundation.document["brands"]
        }
        self._aliases: dict[tuple[str, str], JsonObject] = {}
        for row in foundation.document["aliases"]:
            key = (str(row["retailer_id"]), str(row["alias_normalized"]))
            self._aliases.setdefault(key, dict(row))

    @classmethod
    def from_repository(
        cls,
        repository_root: Path,
        retailer_versions: dict[str, str] | None = None,
    ) -> GovernedBrandResolver:
        catalog = FileRetailerPackCatalog(repository_root)
        if retailer_versions is None:
            packs = catalog.active_versions()
        else:
            packs = {
                retailer_id: catalog.get(retailer_id, version)
                for retailer_id, version in retailer_versions.items()
            }
        refs = {
            (
                str(pack.document["brand_foundation"]["id"]),
                str(pack.document["brand_foundation"]["version"]),
            )
            for pack in packs.values()
        }
        if len(refs) != 1:
            raise ContractError("selected Retailer Packs must reference one brand foundation")
        foundation_id, foundation_version = refs.pop()
        foundation = BrandFoundationLoader(repository_root).load(foundation_id, foundation_version)
        return cls(packs, foundation)

    def with_overrides(self, overrides: list[BrandDecisionOverride]) -> GovernedBrandResolver:
        indexed = {
            (row.retailer_id, normalize_brand_name(row.normalized_brand)): row for row in overrides
        }
        return GovernedBrandResolver(
            self._packs,
            self.foundation,
            overrides=indexed,
        )

    def resolve(self, retailer_id: str, observed_brand: str | None) -> BrandResolution:
        observed = str(observed_brand or "").strip()
        normalized = normalize_brand_name(observed)
        override = self._overrides.get((retailer_id, normalized))
        row = self._canonical.get((retailer_id, normalized))
        method: Literal["exact_canonical", "exact_alias", "legacy_alias"] = "exact_canonical"
        alias: JsonObject | None = None
        if row is None:
            alias = self._aliases.get((retailer_id, normalized))
            if alias is not None:
                row = self._brands_by_id[str(alias["canonical_brand_id"])]
                method = "legacy_alias" if str(alias["status"]) == "Legacy" else "exact_alias"
        if override is not None:
            return self._override_resolution(retailer_id, observed, normalized, row, override)
        if row is None or retailer_id not in self._packs:
            return self._unresolved(retailer_id, observed, normalized)
        eligible = self._strict_eligible(row) and method != "legacy_alias"
        return self._resolved(retailer_id, observed, normalized, row, method, eligible)

    def provenance(self, retailer_ids: list[str]) -> list[JsonObject]:
        rows = [
            {
                "retailer_id": retailer_id,
                "version": self._packs[retailer_id].version,
                "checksum_sha256": self._packs[retailer_id].checksum,
                "brand_foundation": {
                    "id": self.foundation.id,
                    "version": self.foundation.version,
                    "checksum_sha256": self.foundation.checksum,
                },
            }
            for retailer_id in retailer_ids
            if retailer_id in self._packs
        ]
        return rows

    def _strict_eligible(self, row: JsonObject) -> bool:
        pack = self._packs[str(row["retailer_id"])]
        policy = pack.document["brand_policy"]
        return bool(row["in_private_label_matching"]) and all(
            (
                str(row["review_status"]) == "Approved",
                str(row["status"]) in set(policy["eligible_statuses"]),
                str(row["brand_class"]) in set(policy["eligible_classes"]),
            )
        )

    def _resolved(
        self,
        retailer_id: str,
        observed: str,
        normalized: str,
        row: JsonObject,
        method: Literal["exact_canonical", "exact_alias", "legacy_alias"],
        strict_private_label: bool,
    ) -> BrandResolution:
        bucket = str(row["brand_bucket"])
        role: BrandRole = (
            "private_label"
            if strict_private_label
            else "regional"
            if bucket == "Regional"
            else "national"
            if bucket == "National"
            else "unclassified"
        )
        return BrandResolution(
            retailer_id=retailer_id,
            observed_brand=observed,
            normalized_brand=normalized,
            status="resolved",
            resolution_method=method,
            canonical_brand_id=str(row["brand_id"]),
            canonical_brand_name=str(row["brand_name"]),
            role=role,
            strict_private_label=strict_private_label,
            brand_bucket=bucket,
            brand_class=str(row["brand_class"]),
            ownership_model=str(row["ownership_model"]),
            competitive_brand_role=str(row["competitive_brand_role"]),
            review_status=str(row["review_status"]),
            temporal_status=str(row["status"]),
            confidence=str(row["confidence"]),
            matching_priority=str(row["matching_priority"]),
            foundation_id=self.foundation.id,
            foundation_version=self.foundation.version,
            foundation_checksum=self.foundation.checksum,
        )

    def _override_resolution(
        self,
        retailer_id: str,
        observed: str,
        normalized: str,
        row: JsonObject | None,
        override: BrandDecisionOverride,
    ) -> BrandResolution:
        base = (
            self._resolved(retailer_id, observed, normalized, row, "exact_canonical", False)
            if row is not None
            else self._unresolved(retailer_id, observed, normalized)
        )
        confirmed = override.decision == "confirmed"
        return replace(
            base,
            status="resolved" if confirmed or row is not None else "unresolved",
            resolution_method="governed_override",
            canonical_brand_name=(
                (base.canonical_brand_name or override.display_brand)
                if confirmed
                else base.canonical_brand_name
            ),
            role=override.role if confirmed else "unclassified",
            strict_private_label=confirmed and override.role == "private_label",
            override_decision=override.decision,
        )

    def _unresolved(self, retailer_id: str, observed: str, normalized: str) -> BrandResolution:
        return BrandResolution(
            retailer_id=retailer_id,
            observed_brand=observed,
            normalized_brand=normalized,
            status="unresolved",
            resolution_method="unresolved",
            canonical_brand_id=None,
            canonical_brand_name=None,
            role="unclassified",
            strict_private_label=False,
            brand_bucket=None,
            brand_class=None,
            ownership_model=None,
            competitive_brand_role=None,
            review_status=None,
            temporal_status=None,
            confidence=None,
            matching_priority=None,
            foundation_id=self.foundation.id,
            foundation_version=self.foundation.version,
            foundation_checksum=self.foundation.checksum,
        )
