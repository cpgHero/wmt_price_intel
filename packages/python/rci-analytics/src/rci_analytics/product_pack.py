"""Product Pack loading, semantic validation, and immutable persistence."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from rci_contracts import ContractError, validate_instance
from rci_product_packs import ProductPackCatalog

JsonObject = dict[str, Any]
_FORMULA_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
)


def _checksum(document: JsonObject) -> str:
    canonical = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class ProductPack:
    id: str
    name: str
    version: str
    checksum: str
    document: JsonObject

    @property
    def attributes(self) -> tuple[JsonObject, ...]:
        return tuple(dict(value) for value in self.document["attributes"])

    @property
    def matching_profiles(self) -> tuple[JsonObject, ...]:
        return tuple(dict(value) for value in self.document["matching_profiles"])

    @property
    def matching_v2(self) -> JsonObject | None:
        value = self.document.get("matching_v2")
        return dict(value) if isinstance(value, dict) else None

    @property
    def reporting(self) -> JsonObject:
        return dict(self.document["reporting"])

    @property
    def report_blueprint(self) -> JsonObject:
        return dict(self.reporting["report_blueprint"])

    def profile(self, profile_id: str) -> JsonObject:
        try:
            return next(
                profile for profile in self.matching_profiles if profile["id"] == profile_id
            )
        except StopIteration as exc:
            raise ValueError(f"Product Pack has no profile {profile_id!r}") from exc


def primary_exact_profile(
    pack: ProductPack,
    *,
    configured_profile_ids: Iterable[str] | None = None,
) -> JsonObject:
    """Select the Product Pack's first active exact-ZIP decision profile."""

    exact_profiles = [
        profile for profile in pack.matching_profiles if str(profile["geography"]) == "exact_zip"
    ]
    configured = {str(value) for value in configured_profile_ids or ()}
    active_profiles = [profile for profile in exact_profiles if str(profile["id"]) in configured]
    candidates = active_profiles or exact_profiles
    if not candidates:
        raise ValueError("Product Pack has no exact-ZIP comparison profile")
    return candidates[0]


class ProductPackLoader:
    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root

    def load_path(self, path: Path) -> ProductPack:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"could not read Product Pack {path}: {exc}") from exc
        return self.load_document(document, label=str(path))

    def load_document(
        self,
        document: JsonObject,
        *,
        label: str = "<Product Pack>",
        report_blueprint: JsonObject | None = None,
    ) -> ProductPack:
        validate_instance(
            self._root,
            "product-pack.schema.json",
            document,
            label=label,
        )
        self._validate_semantics(document)
        if report_blueprint is None:
            self._validate_report_blueprint(document)
        else:
            self._validate_report_blueprint_document(
                document,
                report_blueprint,
                label=f"{label} report blueprint",
            )
        return ProductPack(
            id=str(document["id"]),
            name=str(document["name"]),
            version=str(document["version"]),
            checksum=_checksum(document),
            document=document,
        )

    def load(self, pack_id: str) -> ProductPack:
        return self.load_path(self._root / "product-packs" / f"{pack_id}.json")

    @staticmethod
    def _validate_semantics(document: JsonObject) -> None:
        attributes = document["attributes"]
        attribute_names = [str(value["name"]) for value in attributes]
        if len(attribute_names) != len(set(attribute_names)):
            raise ContractError("Product Pack attribute names must be unique")
        profiles = document["matching_profiles"]
        profile_ids = [str(value["id"]) for value in profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ContractError("Product Pack matching profile IDs must be unique")
        known = set(attribute_names)
        for attribute in attributes:
            ProductPackLoader._validate_extraction_rules(attribute)
        for profile in profiles:
            dimensions = set(str(value) for value in profile["dimensions"])
            missing = dimensions - known
            if missing:
                raise ContractError(
                    f"profile {profile['id']} references unknown dimensions {sorted(missing)}"
                )
            wildcard_dimensions = set(
                str(value) for value in profile.get("wildcard_dimensions", [])
            )
            invalid_wildcards = wildcard_dimensions - dimensions
            if invalid_wildcards:
                raise ContractError(
                    f"profile {profile['id']} wildcards non-matching dimensions "
                    f"{sorted(invalid_wildcards)}"
                )
            if wildcard_dimensions and profile.get("unknown_policy") != "wildcard_if_one_unknown":
                raise ContractError(
                    f"profile {profile['id']} wildcard dimensions require "
                    "unknown_policy='wildcard_if_one_unknown'"
                )
            if profile["geography"] == "radius" and not profile.get("radius_miles"):
                raise ContractError(f"radius profile {profile['id']} requires radius_miles")
            for constraint_name in (
                "attribute_constraints",
                "benchmark_attribute_constraints",
                "competitor_attribute_constraints",
            ):
                constraints = profile.get(constraint_name, {})
                unknown_constraints = set(constraints) - known
                if unknown_constraints:
                    raise ContractError(
                        f"profile {profile['id']} constrains unknown attributes "
                        f"{sorted(unknown_constraints)}"
                    )
                if any(
                    not isinstance(values, list) or not values for values in constraints.values()
                ):
                    raise ContractError(
                        f"profile {profile['id']} {constraint_name} values must be non-empty arrays"
                    )
            availability_policy = profile.get("availability_policy", "search_presence")
            if availability_policy not in {
                "search_presence",
                "in_stock_only",
                "retailer_specific",
            }:
                raise ContractError(
                    f"profile {profile['id']} has unknown availability policy "
                    f"{availability_policy!r}"
                )
        matching_v2 = document.get("matching_v2")
        if isinstance(matching_v2, dict):
            configured_attributes = set(str(value) for value in matching_v2["attribute_roles"])
            unknown_v2_attributes = configured_attributes - known
            if unknown_v2_attributes:
                raise ContractError(
                    f"matching_v2 references unknown attributes {sorted(unknown_v2_attributes)}"
                )
        strict_required = {
            str(attribute["name"])
            for attribute in attributes
            if attribute.get("required_for_strict") is True
        }
        preferred_profile_id = str(
            document.get("reporting", {})
            .get("decision_rules", {})
            .get("preferred_scorecard_profile_id", "")
        )
        preferred_profile = next(
            (profile for profile in profiles if str(profile["id"]) == preferred_profile_id),
            None,
        )
        if preferred_profile is not None:
            preferred_dimensions = {str(value) for value in preferred_profile.get("dimensions", [])}
            missing_strict = strict_required - preferred_dimensions
            if missing_strict:
                raise ContractError(
                    f"preferred scorecard profile {preferred_profile_id!r} omits strict "
                    f"identity dimensions {sorted(missing_strict)}"
                )
        outputs: set[str] = set()
        for rule in document["normalization"].get("conversion_rules", []):
            if not {"from", "to", "formula"}.issubset(rule):
                raise ContractError("conversion rules require from, to, and formula")
            if str(rule["from"]) not in known:
                raise ContractError(f"conversion source {rule['from']!r} is not an attribute")
            output = str(rule["to"])
            if output in outputs:
                raise ContractError(f"duplicate conversion output {output!r}")
            outputs.add(output)
            ProductPackLoader._validate_formula(str(rule["formula"]), known | {"price"})
        available_metrics = {
            "package_price",
            str(document["normalization"]["primary_display_metric"]),
            *outputs,
        }
        for profile in profiles:
            metric = profile.get("comparison_metric")
            if metric is not None and str(metric) not in available_metrics:
                raise ContractError(
                    f"profile {profile['id']} references unknown comparison metric {metric!r}"
                )
            interval = profile.get("comparison_interval")
            if interval is not None:
                interval_metrics = {
                    str(interval["low_metric"]),
                    str(interval["high_metric"]),
                }
                unknown_interval_metrics = interval_metrics - available_metrics
                if unknown_interval_metrics:
                    raise ContractError(
                        f"profile {profile['id']} references unknown interval metrics "
                        f"{sorted(unknown_interval_metrics)}"
                    )
            if profile["brand_policy"] == "private_label_equivalent":
                private_labels = document.get("brand_rules", {}).get("private_labels", {})
                if not private_labels:
                    raise ContractError(
                        f"private-label profile {profile['id']} requires brand_rules.private_labels"
                    )
            scope_policy = profile.get("relationship_scope_policy")
            if scope_policy:
                if (
                    scope_policy["default_scope_mode"] != "global"
                    and not scope_policy["allow_scoped_reuse"]
                ):
                    raise ContractError(
                        f"profile {profile['id']} selects a footprint scope but disables "
                        "scoped reuse"
                    )
                if (
                    scope_policy["relationship_role"] == "alternative"
                    and scope_policy["default_scope_mode"] == "global"
                ):
                    raise ContractError(
                        f"profile {profile['id']} cannot make a global alternative relationship"
                    )
        brand_rules = document.get("brand_rules", {})
        portfolios = brand_rules.get("portfolios", [])
        portfolio_ids = [str(value["id"]) for value in portfolios]
        if len(portfolio_ids) != len(set(portfolio_ids)):
            raise ContractError("Product Pack brand portfolio IDs must be unique")
        portfolio_brands: set[tuple[str, str]] = set()
        for portfolio in portfolios:
            for retailer_id in portfolio["retailer_ids"]:
                for brand in portfolio["brands"]:
                    key = (str(retailer_id), str(brand).casefold().strip())
                    if key in portfolio_brands:
                        raise ContractError(
                            "Product Pack brand portfolios assign a retailer brand more than once: "
                            f"{retailer_id}/{brand}"
                        )
                    portfolio_brands.add(key)
        for retailer_id, override in document.get("retailer_overrides", {}).items():
            if not isinstance(override, dict):
                raise ContractError(f"retailer override {retailer_id!r} must be an object")
            policy = override.get("catalog_policy")
            if policy not in {None, "allowlist", "rules_only"}:
                raise ContractError(
                    f"retailer override {retailer_id!r} has unknown catalog policy {policy!r}"
                )
            matching_availability = override.get("matching_availability_policy")
            if matching_availability not in {None, "search_presence", "in_stock_only"}:
                raise ContractError(
                    f"retailer override {retailer_id!r} has unknown matching availability "
                    f"policy {matching_availability!r}"
                )
            products = override.get("products", {})
            if not isinstance(products, dict):
                raise ContractError(f"retailer override {retailer_id!r} products must be an object")
            for product_id, rule in products.items():
                if not str(product_id) or not isinstance(rule, dict):
                    raise ContractError(
                        f"retailer override {retailer_id!r} has an invalid product rule"
                    )
                if rule.get("scope") not in {None, "include", "exclude"}:
                    raise ContractError(
                        f"product override {retailer_id!r}/{product_id!r} has invalid scope"
                    )
                values = rule.get("attributes", {})
                if not isinstance(values, dict) or not set(values).issubset(known):
                    raise ContractError(
                        f"product override {retailer_id!r}/{product_id!r} has unknown attributes"
                    )
        ProductPackLoader._validate_reporting(document)

    @staticmethod
    def _validate_reporting(document: JsonObject) -> None:
        reporting = document["reporting"]
        known_profiles = {str(profile["id"]) for profile in document["matching_profiles"]}
        known_portfolios = {
            str(portfolio["id"])
            for portfolio in document.get("brand_rules", {}).get("portfolios", [])
        }
        panel_ids: list[str] = []
        for panel in reporting.get("brand_portfolio_panels", []):
            panel_ids.append(str(panel["id"]))
            if str(panel["profile_id"]) not in known_profiles:
                raise ContractError(
                    f"brand portfolio panel {panel['id']} references unknown profile "
                    f"{panel['profile_id']!r}"
                )
            referenced_portfolios = {
                str(value)
                for field in ("benchmark_portfolio_ids", "competitor_portfolio_ids")
                for value in panel[field]
            }
            missing = referenced_portfolios - known_portfolios
            if missing:
                raise ContractError(
                    f"brand portfolio panel {panel['id']} references unknown portfolios "
                    f"{sorted(missing)}"
                )
        if len(panel_ids) != len(set(panel_ids)):
            raise ContractError("Product Pack brand portfolio panel IDs must be unique")
        decision_rules = reporting.get("decision_rules")
        if decision_rules:
            preferred = str(decision_rules["preferred_scorecard_profile_id"])
            priority = [str(value) for value in decision_rules["profile_priority"]]
            unknown_profiles = {preferred, *priority} - known_profiles
            if unknown_profiles:
                raise ContractError(
                    "Product Pack decision rules reference unknown profiles "
                    f"{sorted(unknown_profiles)}"
                )
            if preferred not in priority:
                raise ContractError(
                    "Product Pack preferred scorecard profile must appear in profile priority"
                )
            if set(priority) != known_profiles:
                missing = known_profiles - set(priority)
                raise ContractError(
                    "Product Pack decision profile priority must include every matching profile; "
                    f"missing {sorted(missing)}"
                )
        weights = reporting["insight_ranking"]["weights"]
        if sum(float(value) for value in weights.values()) <= 0:
            raise ContractError("insight ranking weights must have a positive total")
        rules = reporting["insight_rules"]
        rule_ids = [str(rule["id"]) for rule in rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ContractError("Product Pack insight rule IDs must be unique")
        playbook = reporting["narrative_playbook"]
        lens_ids = [str(lens["id"]) for lens in playbook["decision_lenses"]]
        if len(lens_ids) != len(set(lens_ids)):
            raise ContractError("Product Pack narrative decision-lens IDs must be unique")
        allowed_fields = {
            "matches",
            "unique_geographies",
            "benchmark_lower",
            "competitor_lower",
            "parity",
            "benchmark_lower_rate",
            "competitor_lower_rate",
            "parity_rate",
            "benchmark_median",
            "competitor_median",
            "median_gap",
            "mean_gap",
        }
        allowed_template_fields = {"benchmark", "competitor", "profile", "segment"}
        formatter = Formatter()
        for rule in rules:
            field = str(rule["condition"]["field"])
            if field not in allowed_fields:
                raise ContractError(
                    f"insight rule {rule['id']} references unknown summary field {field!r}"
                )
            for key in ("title_template", "summary_template"):
                fields = {
                    field_name
                    for _, field_name, _, _ in formatter.parse(str(rule[key]))
                    if field_name
                }
                unknown = fields - allowed_template_fields
                if unknown:
                    raise ContractError(
                        f"insight rule {rule['id']} has unknown template fields {sorted(unknown)}"
                    )
            recommendation = rule.get("recommendation")
            if recommendation:
                for key in ("action_template", "rationale_template"):
                    fields = {
                        field_name
                        for _, field_name, _, _ in formatter.parse(str(recommendation[key]))
                        if field_name
                    }
                    unknown = fields - allowed_template_fields
                    if unknown:
                        raise ContractError(
                            f"insight rule {rule['id']} has unknown recommendation fields "
                            f"{sorted(unknown)}"
                        )

    def _validate_report_blueprint(self, document: JsonObject) -> None:
        reference = document["reporting"]["report_blueprint"]
        path = self._root / "report-blueprints" / f"{reference['id']}.json"
        try:
            blueprint = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"could not read report blueprint {path}: {exc}") from exc
        self._validate_report_blueprint_document(document, blueprint, label=str(path))

    def _validate_report_blueprint_document(
        self,
        document: JsonObject,
        blueprint: JsonObject,
        *,
        label: str,
    ) -> None:
        validate_instance(self._root, "report-blueprint.schema.json", blueprint, label=label)
        reference = document["reporting"]["report_blueprint"]
        if blueprint["id"] != reference["id"] or blueprint["version"] != reference["version"]:
            raise ContractError("Product Pack report blueprint reference does not match")
        if blueprint["product_pack"] != {
            "id": document["id"],
            "version": document["version"],
        }:
            raise ContractError("report blueprint Product Pack reference does not match")

    @staticmethod
    def _validate_extraction_rules(attribute: JsonObject) -> None:
        data_type = str(attribute["data_type"])
        allowed_values = {str(value) for value in attribute.get("allowed_values", [])}
        for rule in attribute.get("extraction_rules", []):
            rule_type = str(rule["type"])
            sources = rule.get("sources", ["text"])
            if any(
                source
                not in {
                    "text",
                    "raw_text",
                    "title",
                    "url",
                    "brand",
                    "retailer_product_id",
                }
                and not str(source).startswith("raw.")
                for source in sources
            ):
                raise ContractError(
                    f"attribute {attribute['name']} uses an unknown extraction source"
                )
            required = {
                "constant": {"value"},
                "field": {"sources"},
                "measurement": {"units"},
                "number_pattern": {"patterns"},
                "term_map": {"values"},
                "boolean_terms": set(),
            }[rule_type]
            missing = required - set(rule)
            if missing:
                raise ContractError(
                    f"attribute {attribute['name']} extraction rule {rule_type!r} "
                    f"requires {sorted(missing)}"
                )
            if rule.get("absence_policy") == "infer_default" and "default" not in rule:
                raise ContractError(
                    f"attribute {attribute['name']} cannot infer an absent value without a default"
                )
            if rule_type in {"measurement", "number_pattern"} and data_type != "number":
                raise ContractError(
                    f"attribute {attribute['name']} uses numeric extraction for {data_type}"
                )
            if rule_type == "boolean_terms" and data_type != "boolean":
                raise ContractError(
                    f"attribute {attribute['name']} uses boolean extraction for {data_type}"
                )
            if rule_type == "number_pattern":
                for pattern in rule["patterns"]:
                    try:
                        compiled = re.compile(str(pattern))
                    except re.error as exc:
                        raise ContractError(
                            f"attribute {attribute['name']} has invalid extraction regex"
                        ) from exc
                    if int(rule.get("group", 1)) > compiled.groups:
                        raise ContractError(
                            f"attribute {attribute['name']} extraction group does not exist"
                        )
            if rule_type == "term_map" and data_type == "enum":
                unknown = set(str(value) for value in rule["values"]) - allowed_values
                default = rule.get("default")
                if default is not None and str(default) not in allowed_values:
                    unknown.add(str(default))
                if unknown:
                    raise ContractError(
                        f"attribute {attribute['name']} maps unknown enum values {sorted(unknown)}"
                    )

    @staticmethod
    def _validate_formula(formula: str, allowed_names: set[str]) -> None:
        try:
            tree = ast.parse(formula, mode="eval")
        except SyntaxError as exc:
            raise ContractError(f"invalid conversion formula {formula!r}") from exc
        if any(not isinstance(node, _FORMULA_NODES) for node in ast.walk(tree)):
            raise ContractError(f"conversion formula {formula!r} contains unsafe syntax")
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        if not names.issubset(allowed_names):
            raise ContractError(
                f"conversion formula {formula!r} uses unknown names {sorted(names - allowed_names)}"
            )


class CatalogProductPackLoader:
    """Validate and materialize an exact Product Pack version from a shared catalog."""

    def __init__(self, repository_root: Path, catalog: ProductPackCatalog) -> None:
        self._loader = ProductPackLoader(repository_root)
        self._catalog = catalog

    async def load(self, pack_id: str, version: str) -> ProductPack:
        record = await self._catalog.get(pack_id, version)
        pack = self._loader.load_document(
            record.document,
            label=f"Product Pack {pack_id}@{version}",
            report_blueprint=record.report_blueprint,
        )
        if pack.checksum != record.checksum:
            raise ContractError(f"Product Pack {pack_id}@{version} checksum does not match")
        return pack


class ProductPackRepository(Protocol):
    async def publish(self, pack: ProductPack) -> ProductPack: ...


class InMemoryProductPackRepository:
    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], ProductPack] = {}

    async def publish(self, pack: ProductPack) -> ProductPack:
        key = (pack.id, pack.version)
        existing = self._versions.get(key)
        if existing is not None and existing.checksum != pack.checksum:
            raise ValueError(f"Product Pack {pack.id}@{pack.version} is immutable")
        self._versions[key] = pack
        return pack


class PostgresProductPackRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def publish(self, pack: ProductPack) -> ProductPack:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO product_pack (id, name)
                    VALUES (:id, :name)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                    """
                ),
                {"id": pack.id, "name": pack.name},
            )
            existing = (
                await connection.execute(
                    text(
                        """
                        SELECT checksum FROM product_pack_version
                        WHERE product_pack_id = :id AND version = :version
                        FOR UPDATE
                        """
                    ),
                    {"id": pack.id, "version": pack.version},
                )
            ).scalar_one_or_none()
            if existing is not None:
                if str(existing) != pack.checksum:
                    raise ValueError(f"Product Pack {pack.id}@{pack.version} is immutable")
                return pack
            await connection.execute(
                text(
                    """
                    INSERT INTO product_pack_version (
                      product_pack_id, version, schema_version, config, checksum
                    ) VALUES (
                      :id, :version, '1.0.0', CAST(:config AS jsonb), :checksum
                    )
                    """
                ),
                {
                    "id": pack.id,
                    "version": pack.version,
                    "config": json.dumps(pack.document, sort_keys=True),
                    "checksum": pack.checksum,
                },
            )
        return pack
