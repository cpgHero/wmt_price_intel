"""Immutable Retailer Pack and brand-foundation loading and resolution."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
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
    distribution_scope: str | None
    core_region: str | None
    home_state: str | None
    primary_category: str | None
    category_tags: str | None
    owner_or_marketer: str | None
    category_context: str | None
    is_priority_brand: bool
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
            "distribution_scope": self.distribution_scope,
            "core_region": self.core_region,
            "home_state": self.home_state,
            "primary_category": self.primary_category,
            "category_tags": self.category_tags,
            "owner_or_marketer": self.owner_or_marketer,
            "category_context": self.category_context,
            "is_priority_brand": self.is_priority_brand,
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
    canonical_brand_id: str | None = None
    canonical_brand_name: str | None = None


@dataclass(frozen=True, slots=True)
class BrandCandidateSuggestion:
    canonical_brand_id: str
    canonical_brand_name: str
    role: BrandRole
    strict_private_label: bool
    retailer_scope: str
    confidence_score: int
    rationale: Literal[
        "quarantined_alias_conflict",
        "same_core_name",
        "name_prefix",
        "token_overlap",
        "spelling_similarity",
    ]
    brand_bucket: str
    brand_class: str
    primary_category: str | None
    core_region: str | None

    def to_record(self) -> JsonObject:
        return {
            "canonical_brand_id": self.canonical_brand_id,
            "canonical_brand_name": self.canonical_brand_name,
            "role": self.role,
            "strict_private_label": self.strict_private_label,
            "retailer_scope": self.retailer_scope,
            "confidence_score": self.confidence_score,
            "rationale": self.rationale,
            "brand_bucket": self.brand_bucket,
            "brand_class": self.brand_class,
            "primary_category": self.primary_category,
            "core_region": self.core_region,
        }


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
        active: dict[str, RetailerPack] = {}
        for record in self.versions():
            current = active.get(record.id)
            if current is None or tuple(map(int, record.version.split("."))) > tuple(
                map(int, current.version.split("."))
            ):
                active[record.id] = record
        return active


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
        external_names: set[tuple[str, str]] = set()
        for brand in document.get("external_brands", []):
            brand_id = str(brand["brand_id"])
            normalized = str(brand["brand_name_normalized"])
            category_context = normalize_brand_name(str(brand.get("category_context") or ""))
            canonical_key = (normalized, category_context)
            if brand_id in brand_ids:
                raise ContractError(f"duplicate brand ID {brand_id!r}")
            if canonical_key in external_names:
                raise ContractError(f"duplicate global canonical brand {canonical_key!r}")
            brand_ids.add(brand_id)
            external_names.add(canonical_key)
            retailer_by_brand[brand_id] = "__global__"
        external_ids = {str(brand["brand_id"]) for brand in document.get("external_brands", [])}
        priority_ids = [str(value) for value in document.get("priority_brand_ids", [])]
        unknown_priority_ids = sorted(set(priority_ids) - external_ids)
        if unknown_priority_ids:
            raise ContractError(
                f"priority list references unknown external brands {unknown_priority_ids!r}"
            )
        if len(priority_ids) != len(set(priority_ids)):
            raise ContractError("priority brand IDs must be unique")
        presence_ids = [str(row["brand_id"]) for row in document.get("retailer_presence", [])]
        if len(presence_ids) != len(set(presence_ids)):
            raise ContractError("retailer presence rows must be unique per brand")
        unknown_presence_ids = sorted(set(presence_ids) - external_ids)
        if unknown_presence_ids:
            raise ContractError(
                f"retailer presence references unknown external brands {unknown_presence_ids!r}"
            )
        source_ids = {str(row["source_id"]) for row in document.get("source_registry", [])}
        for brand in document.get("external_brands", []):
            source_id = str(brand["primary_source_id"])
            if source_id not in source_ids:
                raise ContractError(
                    f"external brand {brand['brand_id']!r} references unknown source {source_id!r}"
                )
        alias_ids: set[str] = set()
        aliases: dict[tuple[str, str, str], str] = {}
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
            alias_key = (
                retailer_id,
                str(alias["alias_normalized"]),
                normalize_brand_name(str(alias.get("category_context") or "")),
            )
            existing = aliases.get(alias_key)
            if existing is not None and existing != canonical_brand_id:
                raise ContractError(f"ambiguous exact alias {alias_key!r}")
            aliases[alias_key] = canonical_brand_id
        for conflict in document.get("alias_conflicts", []):
            key = (str(conflict["retailer_id"]), str(conflict["alias_normalized"]))
            if any(alias_key[:2] == key for alias_key in aliases):
                raise ContractError(f"quarantined alias conflict remains resolvable {key!r}")
            candidate_ids = {str(value) for value in conflict["candidate_brand_ids"]}
            unknown_candidates = sorted(candidate_ids - brand_ids)
            if unknown_candidates:
                raise ContractError(
                    f"alias conflict references unknown brands {unknown_candidates!r}"
                )


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
            str(row["brand_id"]): dict(row)
            for row in [
                *foundation.document["brands"],
                *foundation.document.get("external_brands", []),
            ]
        }
        self._canonical = {
            (str(row["retailer_id"]), str(row["brand_name_normalized"])): dict(row)
            for row in foundation.document["brands"]
        }
        self._global_canonical: dict[str, list[JsonObject]] = {}
        for row in foundation.document.get("external_brands", []):
            self._global_canonical.setdefault(str(row["brand_name_normalized"]), []).append(
                dict(row)
            )
        self._aliases: dict[tuple[str, str], list[JsonObject]] = {}
        for row in foundation.document["aliases"]:
            key = (str(row["retailer_id"]), str(row["alias_normalized"]))
            self._aliases.setdefault(key, []).append(dict(row))
        self._global_aliases: dict[str, list[JsonObject]] = {}
        for row in foundation.document.get("aliases", []):
            if str(row["retailer_id"]) == "__global__":
                self._global_aliases.setdefault(str(row["alias_normalized"]), []).append(dict(row))
        self._register_retailer_pack_private_labels()
        self._alias_conflicts = {
            (str(row["retailer_id"]), str(row["alias_normalized"])): tuple(
                str(value) for value in row["candidate_brand_ids"]
            )
            for row in foundation.document.get("alias_conflicts", [])
        }

    def _register_retailer_pack_private_labels(self) -> None:
        """Add versioned retailer-owned brand evidence without mutating the master.

        The broad brand foundation remains the shared source of truth. Retailer Packs
        may close a verified, retailer-specific coverage gap immediately while the
        next foundation release is curated. Resolution remains exact, retailer-scoped,
        and fully represented in Retailer Pack provenance.
        """

        for retailer_id, pack in self._packs.items():
            configured = pack.document["brand_policy"].get("verified_private_labels", [])
            for brand in configured:
                brand_name = str(brand["brand_name"]).strip()
                normalized = normalize_brand_name(brand_name)
                key = (retailer_id, normalized)
                if key in self._canonical:
                    continue
                brand_id = f"retailer_pack__{retailer_id}__{normalized}"
                row: JsonObject = {
                    "brand_id": brand_id,
                    "source_retailer_id": retailer_id,
                    "retailer_id": retailer_id,
                    "retailer": pack.display_name,
                    "retailer_parent": pack.display_name,
                    "brand_name": brand_name,
                    "brand_name_normalized": normalized,
                    "brand_family": brand_name,
                    "brand_bucket": "Private Label",
                    "brand_class": "private_label_owned",
                    "ownership_model": "retailer_owned",
                    "in_private_label_matching": True,
                    "is_grocery_relevant": True,
                    "department_scope": "Retailer-wide",
                    "category_tags": str(brand.get("category_tags") or ""),
                    "competitive_brand_role": f"retailer_{retailer_id}_private_label",
                    "positioning": "Retailer-owned private label",
                    "status": "Active",
                    "retailer_exclusive": True,
                    "matching_priority": "High",
                    "confidence": "Verified",
                    "source_type": "retailer_pack_verified_private_label",
                    "source_url": "https://www.cpghero.com/",
                    "last_verified_at": None,
                    "first_seen_at": None,
                    "last_seen_at": None,
                    "review_status": "Approved",
                    "notes": str(brand["evidence_notes"]),
                }
                self._brands_by_id[brand_id] = row
                self._canonical[key] = row
                for alias_name in brand.get("aliases", []):
                    alias_normalized = normalize_brand_name(str(alias_name))
                    alias_key = (retailer_id, alias_normalized)
                    existing = self._aliases.get(alias_key, [])
                    if existing and {str(value["canonical_brand_id"]) for value in existing} != {
                        brand_id
                    }:
                        raise ContractError(f"ambiguous Retailer Pack brand alias {alias_key!r}")
                    self._aliases.setdefault(alias_key, []).append(
                        {
                            "retailer_id": retailer_id,
                            "alias_normalized": alias_normalized,
                            "canonical_brand_id": brand_id,
                            "status": "Active",
                        }
                    )

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

    def resolve(
        self,
        retailer_id: str,
        observed_brand: str | None,
        *,
        category: str | None = None,
    ) -> BrandResolution:
        observed = str(observed_brand or "").strip()
        normalized = normalize_brand_name(observed)
        override = self._overrides.get((retailer_id, normalized))
        row = self._canonical.get((retailer_id, normalized))
        method: Literal["exact_canonical", "exact_alias", "legacy_alias"] = "exact_canonical"
        alias: JsonObject | None = None
        if row is None:
            alias = self._select_scoped(
                self._aliases.get((retailer_id, normalized), []), category=category
            )
            if alias is not None:
                row = self._brands_by_id[str(alias["canonical_brand_id"])]
                method = "legacy_alias" if str(alias["status"]) == "Legacy" else "exact_alias"
        if row is None:
            row = self._select_scoped(self._global_canonical.get(normalized, []), category=category)
        if row is None:
            alias = self._select_scoped(self._global_aliases.get(normalized, []), category=category)
            if alias is not None:
                row = self._brands_by_id[str(alias["canonical_brand_id"])]
                method = "legacy_alias" if str(alias["status"]) == "Legacy" else "exact_alias"
        if override is not None:
            return self._override_resolution(retailer_id, observed, normalized, row, override)
        if row is None or retailer_id not in self._packs:
            return self._unresolved(retailer_id, observed, normalized)
        eligible = self._strict_eligible(row) and method != "legacy_alias"
        return self._resolved(retailer_id, observed, normalized, row, method, eligible)

    def resolve_from_text(
        self,
        retailer_id: str,
        text: str | None,
        *,
        category: str | None = None,
    ) -> BrandResolution:
        """Resolve one unambiguous governed brand mentioned in product text.

        This is an exact token-boundary fallback for missing or unresolved structured
        brand fields. It deliberately fails closed when text contains more than one
        governed brand, and never uses fuzzy similarity as resolution authority.
        """

        observed_text = str(text or "").strip()
        normalized_text = normalize_brand_name(observed_text)
        if not normalized_text:
            return self._unresolved(retailer_id, "", "")
        padded = f"_{normalized_text}_"
        keys = (
            {
                normalized
                for candidate_retailer, normalized in self._canonical
                if candidate_retailer == retailer_id
            }
            | {
                normalized
                for candidate_retailer, normalized in self._aliases
                if candidate_retailer == retailer_id
            }
            | set(self._global_canonical)
            | set(self._global_aliases)
        )
        matches: dict[str, BrandResolution] = {}
        for candidate in sorted(keys, key=lambda value: (-len(value.split("_")), -len(value))):
            if len(candidate) < 3 or candidate.isdigit() or f"_{candidate}_" not in padded:
                continue
            resolution = self.resolve(retailer_id, candidate, category=category)
            if resolution.status == "resolved" and resolution.canonical_brand_id:
                matches.setdefault(resolution.canonical_brand_id, resolution)
        if len(matches) == 1:
            return next(iter(matches.values()))
        return self._unresolved(retailer_id, observed_text, normalized_text)

    def suggest(
        self,
        retailer_id: str,
        observed_brand: str | None,
        *,
        category: str | None = None,
        limit: int = 3,
    ) -> tuple[BrandCandidateSuggestion, ...]:
        """Return inspectable candidates without changing resolution authority.

        Suggestions are deliberately separate from :meth:`resolve`. Even a very high
        score remains review evidence until a human confirms a governed override.
        Retailer-owned candidates are visible only within their owning retailer.
        """

        if limit < 1:
            return ()
        observed = str(observed_brand or "").strip()
        normalized = normalize_brand_name(observed)
        if (
            not normalized
            or self.resolve(retailer_id, observed, category=category).status == "resolved"
        ):
            return ()

        conflict_ids = self._alias_conflicts.get((retailer_id, normalized), ())
        if conflict_ids:
            return tuple(
                self._suggestion(
                    retailer_id,
                    self._brands_by_id[brand_id],
                    score=100,
                    rationale="quarantined_alias_conflict",
                )
                for brand_id in conflict_ids[:limit]
            )

        candidates = [
            row
            for (candidate_retailer_id, _), row in self._canonical.items()
            if candidate_retailer_id == retailer_id
        ]
        candidates.extend(
            row
            for rows in self._global_canonical.values()
            for row in rows
            if self._category_row_allowed(row, category)
        )
        unique_candidates = {str(row["brand_id"]): row for row in candidates}
        scored: list[BrandCandidateSuggestion] = []
        for row in unique_candidates.values():
            score, rationale = self._candidate_score(
                normalized,
                str(row["brand_name_normalized"]),
                category=category,
                row=row,
            )
            # Below 75, shared retail words such as "dairy", "farm", or "quality"
            # create more review noise than useful identity evidence. Keep those
            # observations unclassified instead of presenting a weak candidate.
            if score < 75:
                continue
            scored.append(
                self._suggestion(
                    retailer_id,
                    row,
                    score=score,
                    rationale=rationale,
                )
            )
        scored.sort(
            key=lambda value: (
                -value.confidence_score,
                value.canonical_brand_name.casefold(),
                value.canonical_brand_id,
            )
        )
        return tuple(scored[:limit])

    @staticmethod
    def _candidate_score(
        observed: str,
        canonical: str,
        *,
        category: str | None,
        row: JsonObject,
    ) -> tuple[
        int, Literal["same_core_name", "name_prefix", "token_overlap", "spelling_similarity"]
    ]:
        observed_tokens = tuple(value for value in observed.split("_") if value)
        canonical_tokens = tuple(value for value in canonical.split("_") if value)
        if not observed_tokens or not canonical_tokens:
            return 0, "spelling_similarity"

        suffixes = {
            "brand",
            "brands",
            "co",
            "company",
            "dairy",
            "farm",
            "farms",
            "food",
            "foods",
            "inc",
            "llc",
        }

        def core(tokens: tuple[str, ...]) -> tuple[str, ...]:
            values = list(tokens)
            while len(values) > 1 and values[-1] in suffixes:
                values.pop()
            return tuple(values)

        observed_core = core(observed_tokens)
        canonical_core = core(canonical_tokens)
        sequence_score = round(100 * SequenceMatcher(None, observed, canonical).ratio())
        observed_set = set(observed_tokens)
        canonical_set = set(canonical_tokens)
        overlap = len(observed_set & canonical_set) / max(len(observed_set | canonical_set), 1)
        token_score = round(100 * overlap)
        score = max(sequence_score, token_score)
        rationale: Literal[
            "same_core_name", "name_prefix", "token_overlap", "spelling_similarity"
        ] = "spelling_similarity"
        if observed_core == canonical_core:
            score = max(score, 94 - 2 * abs(len(observed_tokens) - len(canonical_tokens)))
            rationale = "same_core_name"
        elif (
            observed_tokens == canonical_tokens[: len(observed_tokens)]
            or canonical_tokens == observed_tokens[: len(canonical_tokens)]
        ):
            score = max(score, 91 - 2 * abs(len(observed_tokens) - len(canonical_tokens)))
            rationale = "name_prefix"
        elif observed_set <= canonical_set or canonical_set <= observed_set:
            score = max(score, 84 - abs(len(observed_tokens) - len(canonical_tokens)))
            rationale = "token_overlap"
        elif token_score >= sequence_score:
            rationale = "token_overlap"

        category_key = normalize_brand_name(category or "")
        category_values = normalize_brand_name(
            " ".join(str(row.get(value) or "") for value in ("primary_category", "category_tags"))
        )
        if category_key and category_values:
            category_tokens = set(category_key.split("_"))
            if category_tokens & set(category_values.split("_")):
                score = min(100, score + 2)
        if bool(row.get("is_priority_brand")):
            score = min(100, score + 1)
        return score, rationale

    def _suggestion(
        self,
        retailer_id: str,
        row: JsonObject,
        *,
        score: int,
        rationale: Literal[
            "quarantined_alias_conflict",
            "same_core_name",
            "name_prefix",
            "token_overlap",
            "spelling_similarity",
        ],
    ) -> BrandCandidateSuggestion:
        strict_private_label = self._strict_eligible(row)
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
        return BrandCandidateSuggestion(
            canonical_brand_id=str(row["brand_id"]),
            canonical_brand_name=str(row["brand_name"]),
            role=role,
            strict_private_label=strict_private_label,
            retailer_scope=(
                str(row.get("retailer_id") or "global")
                if str(row.get("retailer_id") or "__global__") != "__global__"
                else "global"
            ),
            confidence_score=max(0, min(100, score)),
            rationale=rationale,
            brand_bucket=bucket,
            brand_class=str(row["brand_class"]),
            primary_category=(
                str(row["primary_category"]) if row.get("primary_category") else None
            ),
            core_region=str(row["core_region"]) if row.get("core_region") else None,
        )

    @staticmethod
    def _category_alias_allowed(alias: JsonObject, category: str | None) -> bool:
        if str(alias.get("matching_rule")) != "exact_normalized_then_category_gate":
            return True
        if not category:
            return False
        expected = {
            normalize_brand_name(value)
            for value in str(alias.get("category_context") or "").split(";")
            if value.strip()
        }
        observed = normalize_brand_name(category)
        return any(value in observed or observed in value for value in expected)

    @staticmethod
    def _category_row_allowed(row: JsonObject, category: str | None) -> bool:
        context = str(row.get("category_context") or "").strip()
        if not context:
            return True
        if not category:
            return False
        expected = normalize_brand_name(context)
        observed = normalize_brand_name(category)
        return (
            expected in observed
            or observed in expected
            or bool(set(expected.split("_")) & set(observed.split("_")))
        )

    def _select_scoped(
        self,
        rows: list[JsonObject],
        *,
        category: str | None,
    ) -> JsonObject | None:
        allowed = [
            row
            for row in rows
            if self._category_row_allowed(row, category)
            and self._category_alias_allowed(row, category)
        ]
        if not allowed:
            return None
        scoped = [row for row in allowed if str(row.get("category_context") or "").strip()]
        candidates = scoped or allowed
        canonical_ids = {
            str(row.get("canonical_brand_id") or row["brand_id"]) for row in candidates
        }
        if len(canonical_ids) != 1:
            return None
        return candidates[0]

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
        if "retailer_id" not in row or str(row["retailer_id"]) == "__global__":
            return False
        pack = self._packs[str(row["retailer_id"])]
        policy = pack.document["brand_policy"]
        return bool(row["in_private_label_matching"]) and all(
            (
                str(row["ownership_model"]) == "retailer_owned",
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
            ownership_model=(str(row["ownership_model"]) if row.get("ownership_model") else None),
            competitive_brand_role=(
                str(row["competitive_brand_role"]) if row.get("competitive_brand_role") else None
            ),
            review_status=str(row["review_status"]) if row.get("review_status") else None,
            temporal_status=str(row["status"]),
            confidence=str(row["confidence"]),
            matching_priority=str(row["matching_priority"]),
            distribution_scope=(
                str(row["distribution_scope"]) if row.get("distribution_scope") else None
            ),
            core_region=str(row["core_region"]) if row.get("core_region") else None,
            home_state=str(row["home_state"]) if row.get("home_state") else None,
            primary_category=(
                str(row["primary_category"]) if row.get("primary_category") else None
            ),
            category_tags=str(row["category_tags"]) if row.get("category_tags") else None,
            owner_or_marketer=(
                str(row["owner_or_marketer"]) if row.get("owner_or_marketer") else None
            ),
            category_context=(
                str(row["category_context"]) if row.get("category_context") else None
            ),
            is_priority_brand=bool(row.get("is_priority_brand", False)),
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
        governed_row = (
            self._brands_by_id.get(override.canonical_brand_id)
            if override.canonical_brand_id
            else None
        )
        if governed_row is not None:
            governed_retailer = str(governed_row.get("retailer_id") or "__global__")
            if governed_retailer not in {"__global__", retailer_id}:
                governed_row = None
        if governed_row is not None and override.decision == "confirmed":
            row = governed_row
        base = (
            self._resolved(
                retailer_id,
                observed,
                normalized,
                row,
                "exact_canonical",
                self._strict_eligible(row),
            )
            if row is not None
            else self._unresolved(retailer_id, observed, normalized)
        )
        confirmed = override.decision == "confirmed"
        return replace(
            base,
            status="resolved" if confirmed or row is not None else "unresolved",
            resolution_method="governed_override",
            canonical_brand_name=(
                (
                    base.canonical_brand_name
                    or override.canonical_brand_name
                    or override.display_brand
                )
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
            distribution_scope=None,
            core_region=None,
            home_state=None,
            primary_category=None,
            category_tags=None,
            owner_or_marketer=None,
            category_context=None,
            is_priority_brand=False,
            foundation_id=self.foundation.id,
            foundation_version=self.foundation.version,
            foundation_checksum=self.foundation.checksum,
        )
