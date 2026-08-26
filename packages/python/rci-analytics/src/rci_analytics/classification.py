"""Configuration-driven deterministic scope, attribute, and metric classification."""

from __future__ import annotations

import ast
import re
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from rci_analytics.models import ClassifiedOffer, JsonObject, NormalizedOffer
from rci_analytics.package_semantics import effective_package_measure
from rci_analytics.product_pack import ProductPack
from rci_retailer_packs import GovernedBrandResolver

_GENERIC_NAME_WORDS = {"fresh", "raw", "whole", "product", "products"}


def _normalized_text(value: str) -> str:
    # Preserve decimal points so a source value such as ``2.25 lb`` cannot be
    # normalized into ``2 25 lb`` and then misread as a 25-pound package.
    protected = re.sub(r"(?<=\d)\.(?=\d)", "decimalpoint", value.casefold())
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", protected).split())
    return normalized.replace("decimalpoint", ".")


def _normalized_evidence_text(value: str) -> str:
    """Normalize current title evidence while preserving percentages and decimals."""

    protected = re.sub(r"(?<=\d)\.(?=\d)", "decimalpoint", value.casefold())
    normalized = " ".join(re.sub(r"[^a-z0-9%]+", " ", protected).split())
    return normalized.replace("decimalpoint", ".")


def _singular(value: str) -> str:
    if value.endswith("ies") and len(value) > 3:
        return f"{value[:-3]}y"
    if value.endswith("s") and len(value) > 3:
        return value[:-1]
    return value


def _target_terms(pack: ProductPack) -> set[str]:
    configured = pack.document["scope"].get("target_terms", [])
    if configured:
        return {_normalized_text(str(value)) for value in configured}
    words = [
        word for word in _normalized_text(pack.name).split() if word not in _GENERIC_NAME_WORDS
    ]
    target = words[-1] if words else _normalized_text(pack.id).split()[-1]
    return {target, _singular(target)}


def _exclusion_patterns(pack: ProductPack) -> tuple[str, ...]:
    scope = pack.document["scope"]
    explicit = scope.get("hard_exclusion_patterns", [])
    return tuple(
        sorted(
            (_normalized_text(str(value)) for value in explicit),
            key=lambda value: (-len(value.split()), value),
        )
    )


def _contains_pattern(text: str, pattern: str) -> bool:
    return bool(_compile_term_pattern(pattern).search(text))


def _compile_term_pattern(pattern: str) -> re.Pattern[str]:
    expression = r"\s+".join(rf"{re.escape(word)}(?:s|es)?" for word in pattern.split())
    return re.compile(rf"\b{expression}\b")


class FormulaEvaluator:
    def evaluate(self, formula: str, values: dict[str, Decimal | None]) -> Decimal | None:
        try:
            tree = ast.parse(formula, mode="eval")
            return self._node(tree.body, values)
        except (SyntaxError, ValueError, InvalidOperation, DivisionByZero, ZeroDivisionError):
            return None

    def _node(self, node: ast.AST, values: dict[str, Decimal | None]) -> Decimal:
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            value = values.get(node.id)
            if value is None:
                raise ValueError(f"formula input {node.id!r} is unavailable")
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self._node(node.operand, values)
        if isinstance(node, ast.BinOp):
            left = self._node(node.left, values)
            right = self._node(node.right, values)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise ValueError("conversion formula contains an unsupported expression")


class OfferClassifier:
    def __init__(
        self,
        pack: ProductPack,
        brand_resolver: GovernedBrandResolver | None = None,
    ) -> None:
        self.pack = pack
        self._brand_resolver = brand_resolver
        self._targets = _target_terms(pack)
        self._exclusions = _exclusion_patterns(pack)
        self._target_patterns = tuple(_compile_term_pattern(term) for term in sorted(self._targets))
        self._exclusion_patterns = tuple(
            (value, _compile_term_pattern(value)) for value in self._exclusions
        )
        self._formulas = FormulaEvaluator()
        self._term_maps: dict[int, tuple[tuple[re.Pattern[str], Any], ...]] = {}
        self._boolean_terms: dict[
            int, tuple[tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]]
        ] = {}
        self._measurement_rules: dict[int, tuple[re.Pattern[str], dict[str, Decimal]]] = {}
        self._number_patterns: dict[int, tuple[re.Pattern[str], ...]] = {}
        self._compile_rules()

    def _compile_rules(self) -> None:
        for definition in self.pack.attributes:
            for rule in definition.get("extraction_rules", []):
                rule_type = str(rule["type"])
                if rule_type == "term_map":
                    candidates = [
                        (_normalized_text(str(term)), value)
                        for value, terms in rule.get("values", {}).items()
                        for term in terms
                    ]
                    candidates.sort(key=lambda item: (-len(item[0].split()), -len(item[0])))
                    self._term_maps[id(rule)] = tuple(
                        (_compile_term_pattern(term), value) for term, value in candidates
                    )
                elif rule_type == "boolean_terms":
                    self._boolean_terms[id(rule)] = (
                        self._compile_term_list(rule.get("true_terms", [])),
                        self._compile_term_list(rule.get("false_terms", [])),
                    )
                elif rule_type == "measurement":
                    units = {
                        _normalized_text(str(key)): Decimal(str(value))
                        for key, value in rule["units"].items()
                    }
                    aliases = sorted(
                        units,
                        key=lambda value: (-len(value.split()), -len(value)),
                    )
                    unit_expression = "|".join(
                        r"\s+".join(re.escape(word) for word in alias.split()) for alias in aliases
                    )
                    self._measurement_rules[id(rule)] = (
                        re.compile(rf"(?<![\d.])(\d+(?:\.\d+)?)\s*({unit_expression})(?![a-z])"),
                        units,
                    )
                elif rule_type == "number_pattern":
                    self._number_patterns[id(rule)] = tuple(
                        re.compile(str(pattern), re.IGNORECASE)
                        for pattern in rule.get("patterns", [])
                    )

    @staticmethod
    def _compile_term_list(values: Any) -> tuple[re.Pattern[str], ...]:
        candidates = sorted(
            (_normalized_text(str(value)) for value in values),
            key=lambda value: (-len(value.split()), -len(value)),
        )
        return tuple(_compile_term_pattern(value) for value in candidates)

    def classify(self, offer: NormalizedOffer) -> ClassifiedOffer:
        retailer_override, product_override = self._product_override(offer)
        in_scope, scope_reason = self._scope(offer, retailer_override, product_override)
        attributes: JsonObject = {}
        provenance: JsonObject = {}
        review: list[str] = []
        if in_scope:
            for definition in self.pack.attributes:
                name = str(definition["name"])
                value, evidence = self._extract_attribute(name, definition, offer, product_override)
                attributes[name] = value
                provenance[name] = evidence
                if bool(definition.get("required_for_strict")) and value is None:
                    review.append(f"required attribute {name} is unresolved")
            attributes["_attribute_provenance"] = provenance
            brand_evidence = self.resolve_brand_evidence(
                offer,
                observed_brand=attributes.get("brand") or offer.brand,
                evidence_text=offer.title,
            )
            if brand_evidence is not None:
                governance, canonical_brand, resolution_source = brand_evidence
                attributes["_brand_governance"] = governance
                if canonical_brand:
                    attributes["brand"] = canonical_brand
                    provenance["brand"] = resolution_source

        metrics = self._metrics(offer, attributes) if in_scope else {}
        return ClassifiedOffer(
            offer=offer,
            in_scope=in_scope,
            scope_reason=scope_reason,
            attributes=attributes,
            metrics=metrics,
            review_reasons=tuple(review),
        )

    def resolve_brand_evidence(
        self,
        offer: NormalizedOffer,
        *,
        observed_brand: Any,
        evidence_text: str | None,
    ) -> tuple[JsonObject, str | None, str] | None:
        """Resolve brand identity from a bounded, product-only evidence surface.

        Retailer breadcrumb/category text must never establish private-label
        ownership. Callers enriching from PDP data should therefore pass only the
        explicit PDP brand and product name, not category paths or descriptions.
        """

        if self._brand_resolver is None:
            return None
        observed = str(observed_brand).strip() if observed_brand not in (None, "") else None
        resolution = self._brand_resolver.resolve(
            offer.retailer_id,
            observed,
            category=self.pack.name,
        )
        resolution_source: str = resolution.resolution_method
        if resolution.status != "resolved":
            title_resolution = self._brand_resolver.resolve_from_text(
                offer.retailer_id,
                evidence_text,
                category=self.pack.name,
            )
            canonical_in_observed = False
            if observed and title_resolution.canonical_brand_name:
                observed_text = f" {_normalized_text(observed)} "
                canonical_text = f" {_normalized_text(title_resolution.canonical_brand_name)} "
                canonical_in_observed = canonical_text in observed_text
            # A present structured brand is stronger identity evidence than an
            # unrelated word in the product title. A title result may refine that
            # field only when the governed canonical name is explicitly contained
            # in it (for example, "Nature Made Nutritional Products").
            if title_resolution.status == "resolved" and (
                observed is None or canonical_in_observed
            ):
                resolution = title_resolution
                resolution_source = "retailer_pack_title"
        return resolution.to_record(), resolution.canonical_brand_name, resolution_source

    def classify_many(self, offers: list[NormalizedOffer]) -> list[ClassifiedOffer]:
        return [self.classify(offer) for offer in offers]

    def _product_override(self, offer: NormalizedOffer) -> tuple[JsonObject, JsonObject | None]:
        retailer_overrides = self.pack.document.get("retailer_overrides", {})
        retailer = retailer_overrides.get(offer.retailer_id, {})
        products = retailer.get("products", {})
        product = products.get(offer.retailer_product_id)
        return retailer, product

    def _scope(
        self,
        offer: NormalizedOffer,
        retailer_override: JsonObject,
        product_override: JsonObject | None,
    ) -> tuple[bool, str | None]:
        if retailer_override.get("catalog_policy") == "allowlist" and product_override is None:
            return False, "retailer product is not in the configured allowlist"
        if product_override is not None and product_override.get("scope") == "exclude":
            return False, "retailer product is explicitly excluded"
        title = _normalized_text(offer.title)
        text = self._source_text(offer)
        explicit_include = (
            product_override is not None and product_override.get("scope") == "include"
        )
        if not explicit_include and not any(
            pattern.search(title) for pattern in self._target_patterns
        ):
            target_attribute = self.pack.document["scope"].get("target_attribute")
            definition = next(
                (
                    attribute
                    for attribute in self.pack.attributes
                    if str(attribute["name"]) == str(target_attribute)
                ),
                None,
            )
            target_value = (
                self._extract_attribute(str(target_attribute), definition, offer, product_override)[
                    0
                ]
                if definition is not None
                else None
            )
            if target_value is None:
                return False, "target product term or governed target attribute absent"
        if not explicit_include:
            for value, pattern in self._exclusion_patterns:
                if pattern.search(text):
                    return False, f"excluded scope pattern: {value}"
        if self.pack.document["scope"].get("require_positive_price") and (
            offer.price is None or offer.price <= 0
        ):
            return False, "positive USD price is required"
        availability_policy = self.pack.document["scope"].get("availability_policy")
        if availability_policy == "in_stock_only" and offer.in_stock is False:
            return False, "explicitly out of stock"
        return True, None

    @staticmethod
    def _source_text(offer: NormalizedOffer) -> str:
        path = urlsplit(offer.product_url).path if offer.product_url else ""
        return _normalized_text(f"{offer.title} {path}")

    def _extract_attribute(
        self,
        name: str,
        definition: JsonObject,
        offer: NormalizedOffer,
        product_override: JsonObject | None,
    ) -> tuple[Any, str]:
        if product_override is not None:
            attributes = product_override.get("attributes", {})
            if name in attributes:
                return attributes[name], "product_pack_override"
        for rule in definition.get("extraction_rules", []):
            value = self._apply_extraction_rule(rule, definition, offer)
            if value is not None:
                return value, (
                    "product_pack_constant" if str(rule.get("type")) == "constant" else "search"
                )
            if rule.get("default") is not None:
                # Missing evidence is unknown. A Product Pack may explicitly opt into
                # a default only when the absence itself is authoritative evidence.
                if str(rule.get("absence_policy") or "unknown") != "infer_default":
                    return None, "unresolved"
                return self._coerce(rule["default"], definition), "product_pack_default"
        return None, "unresolved"

    def observed_attribute(
        self,
        name: str,
        offer: NormalizedOffer,
        *,
        brand: str | None = None,
    ) -> Any:
        """Extract explicit current title evidence without consulting static overrides."""

        definition = next(
            (attribute for attribute in self.pack.attributes if str(attribute["name"]) == name),
            None,
        )
        if definition is None:
            raise KeyError(f"unknown Product Pack attribute {name!r}")
        title = _normalized_evidence_text(offer.title)
        observed_brand = brand or offer.brand
        if observed_brand:
            normalized_brand = _normalized_evidence_text(observed_brand)
            if normalized_brand:
                title = " ".join(title.replace(normalized_brand, " ").split())
        title_offer = NormalizedOffer(
            offer_id=offer.offer_id,
            retailer_id=offer.retailer_id,
            retailer_product_id=offer.retailer_product_id,
            title=title,
            brand=None,
            price=offer.price,
            currency=offer.currency,
            zipcode=offer.zipcode,
            store_number=offer.store_number,
            latitude=offer.latitude,
            longitude=offer.longitude,
            in_stock=offer.in_stock,
            product_url=None,
            image_url=offer.image_url,
            collected_at=offer.collected_at,
            raw=offer.raw,
            regular_price=offer.regular_price,
            discounted_price=offer.discounted_price,
            is_sponsored=offer.is_sponsored,
        )
        for rule in definition.get("extraction_rules", []):
            if str(rule["type"]) == "term_map":
                matches: list[tuple[int, int, int, Any]] = []
                for value, terms in rule.get("values", {}).items():
                    for term in terms:
                        normalized = _normalized_evidence_text(str(term))
                        expression = r"\s+".join(re.escape(word) for word in normalized.split())
                        if re.search(
                            rf"(?<![a-z0-9]){expression}(?![a-z0-9])",
                            title,
                        ):
                            matches.append(
                                (
                                    len(normalized.split()),
                                    int(any(character.isdigit() for character in normalized)),
                                    len(normalized),
                                    value,
                                )
                            )
                if not matches:
                    value = None
                else:
                    matches.sort(key=lambda row: (-row[0], -row[1], -row[2], str(row[3])))
                    strongest = (matches[0][0], matches[0][1], matches[0][2])
                    strongest_values = {
                        row[3] for row in matches if (row[0], row[1], row[2]) == strongest
                    }
                    value = (
                        self._coerce(next(iter(strongest_values)), definition)
                        if len(strongest_values) == 1
                        else None
                    )
            else:
                value = self._apply_extraction_rule(rule, definition, title_offer)
            if value is not None:
                return value
            if (
                rule.get("default") is not None
                and str(rule.get("absence_policy") or "unknown") == "infer_default"
            ):
                return self._coerce(rule["default"], definition)
        return None

    def _apply_extraction_rule(
        self, rule: JsonObject, definition: JsonObject, offer: NormalizedOffer
    ) -> Any:
        rule_type = str(rule["type"])
        if rule_type == "constant":
            return rule.get("value")
        if rule_type == "field":
            for value in self._source_values(rule, offer):
                if value is not None and str(value).strip():
                    return self._coerce(value, definition)
            return None
        if rule_type == "measurement":
            return self._measurement(rule, definition, offer)
        if rule_type == "number_pattern":
            return self._number_pattern(rule, definition, offer)
        if rule_type == "term_map":
            return self._term_map(rule, definition, offer)
        if rule_type == "boolean_terms":
            text = self._rule_text(rule, offer)
            true_terms, false_terms = self._boolean_terms[id(rule)]
            if self._contains_any(text, true_terms):
                return True
            if self._contains_any(text, false_terms):
                return False
            return None
        raise ValueError(f"unknown extraction rule type {rule_type!r}")

    @staticmethod
    def _coerce(value: Any, definition: JsonObject) -> Any:
        data_type = str(definition["data_type"])
        if data_type == "number":
            try:
                # Retailer titles and PDP fields commonly render thousands
                # separators (for example, "2,500 mcg"). The separator is
                # presentation, not magnitude, so normalize it before Decimal.
                normalized = "".join(str(value).split()).replace(",", "")
                return float(Decimal(normalized).normalize())
            except (InvalidOperation, ValueError):
                return None
        if data_type == "boolean":
            if isinstance(value, bool):
                return value
            normalized = str(value).strip().casefold()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n"}:
                return False
            return None
        if data_type == "array":
            return value if isinstance(value, list) else [value]
        return str(value)

    @staticmethod
    def _source_values(rule: JsonObject, offer: NormalizedOffer) -> tuple[Any, ...]:
        sources = rule.get("sources", ["text"])
        values: list[Any] = []
        raw_keys: dict[str, Any] | None = None
        for source in sources:
            source_name = str(source)
            if source_name in {"text", "raw_text"}:
                path = urlsplit(offer.product_url).path if offer.product_url else ""
                values.append(f"{offer.title} {path}")
            elif source_name == "title":
                values.append(offer.title)
            elif source_name == "url":
                values.append(urlsplit(offer.product_url).path if offer.product_url else None)
            elif source_name == "brand":
                values.append(offer.brand)
            elif source_name == "retailer_product_id":
                values.append(offer.retailer_product_id)
            elif source_name.startswith("raw."):
                if raw_keys is None:
                    raw_keys = {
                        _normalized_text(str(key)): value for key, value in offer.raw.items()
                    }
                values.append(raw_keys.get(_normalized_text(source_name[4:])))
            else:
                raise ValueError(f"unknown extraction source {source_name!r}")
        return tuple(values)

    def _rule_text(self, rule: JsonObject, offer: NormalizedOffer) -> str:
        values = self._source_values(rule, offer)
        text = " ".join(str(value) for value in values if value is not None)
        if "raw_text" in rule.get("sources", []):
            return text
        return _normalized_text(text)

    def _measurement(self, rule: JsonObject, definition: JsonObject, offer: NormalizedOffer) -> Any:
        pattern, units = self._measurement_rules[id(rule)]
        text = self._rule_text(rule, offer)
        match = pattern.search(text)
        if match is None:
            return None
        matched_unit = _normalized_text(match.group(2))
        factor = units[matched_unit]
        return self._coerce(Decimal(match.group(1)) * factor, definition)

    def _number_pattern(
        self, rule: JsonObject, definition: JsonObject, offer: NormalizedOffer
    ) -> Any:
        text = self._rule_text(rule, offer)
        group = int(rule.get("group", 1))
        for pattern in self._number_patterns[id(rule)]:
            match = pattern.search(text)
            if match is not None:
                return self._coerce(match.group(group), definition)
        return None

    def _term_map(self, rule: JsonObject, definition: JsonObject, offer: NormalizedOffer) -> Any:
        text = self._rule_text(rule, offer)
        for pattern, value in self._term_maps[id(rule)]:
            if pattern.search(text):
                return self._coerce(value, definition)
        return None

    @staticmethod
    def _contains_any(text: str, terms: tuple[re.Pattern[str], ...]) -> bool:
        return any(term.search(text) for term in terms)

    def _metrics(self, offer: NormalizedOffer, attributes: JsonObject) -> dict[str, Decimal | None]:
        values: dict[str, Decimal | None] = {"price": offer.price}
        for key, value in attributes.items():
            if isinstance(value, bool):
                continue
            try:
                values[key] = Decimal(str(value)) if value is not None else None
            except InvalidOperation:
                continue
        metrics: dict[str, Decimal | None] = {}
        for rule in self.pack.document["normalization"].get("conversion_rules", []):
            output = str(rule["to"])
            formula_values = dict(values)
            source_measure = str(rule.get("from") or "")
            if source_measure and source_measure in formula_values:
                formula_values[source_measure] = effective_package_measure(
                    offer.title,
                    formula_values[source_measure],
                )
            metrics[output] = self._formulas.evaluate(str(rule["formula"]), formula_values)
        return metrics
