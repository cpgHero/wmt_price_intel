"""Configuration-driven deterministic scope, attribute, and metric classification."""

from __future__ import annotations

import ast
import re
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from rci_analytics.models import ClassifiedOffer, JsonObject, NormalizedOffer
from rci_analytics.product_pack import ProductPack

_GENERIC_NAME_WORDS = {"fresh", "raw", "whole", "product", "products"}


def _normalized_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


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
    expression = r"\s+".join(rf"{re.escape(word)}(?:s|es)?" for word in pattern.split())
    return bool(re.search(rf"\b{expression}\b", text))


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
    def __init__(self, pack: ProductPack) -> None:
        self.pack = pack
        self._targets = _target_terms(pack)
        self._exclusions = _exclusion_patterns(pack)
        self._formulas = FormulaEvaluator()

    def classify(self, offer: NormalizedOffer) -> ClassifiedOffer:
        retailer_override, product_override = self._product_override(offer)
        in_scope, scope_reason = self._scope(offer, retailer_override, product_override)
        attributes: JsonObject = {}
        review: list[str] = []
        if in_scope:
            for definition in self.pack.attributes:
                name = str(definition["name"])
                value = self._extract_attribute(name, definition, offer, product_override)
                attributes[name] = value
                if bool(definition.get("required_for_strict")) and value is None:
                    review.append(f"required attribute {name} is unresolved")

        metrics = self._metrics(offer, attributes) if in_scope else {}
        return ClassifiedOffer(
            offer=offer,
            in_scope=in_scope,
            scope_reason=scope_reason,
            attributes=attributes,
            metrics=metrics,
            review_reasons=tuple(review),
        )

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
        if not any(re.search(rf"\b{re.escape(term)}\b", title) for term in self._targets):
            return False, "target product term absent"
        for pattern in self._exclusions:
            if _contains_pattern(text, pattern):
                return False, f"excluded scope pattern: {pattern}"
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
    ) -> Any:
        if product_override is not None:
            attributes = product_override.get("attributes", {})
            if name in attributes:
                return attributes[name]
        for rule in definition.get("extraction_rules", []):
            value = self._apply_extraction_rule(rule, definition, offer)
            if value is not None:
                return value
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
            true_terms = tuple(str(value) for value in rule.get("true_terms", []))
            false_terms = tuple(str(value) for value in rule.get("false_terms", []))
            if self._contains_any(text, true_terms):
                return True
            if self._contains_any(text, false_terms):
                return False
            return rule.get("default")
        raise ValueError(f"unknown extraction rule type {rule_type!r}")

    @staticmethod
    def _coerce(value: Any, definition: JsonObject) -> Any:
        data_type = str(definition["data_type"])
        if data_type == "number":
            try:
                return float(Decimal(str(value)).normalize())
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
        raw_keys = {_normalized_text(str(key)): value for key, value in offer.raw.items()}
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
            elif source_name.startswith("raw."):
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
        units = {str(key): Decimal(str(value)) for key, value in rule["units"].items()}
        aliases = sorted(
            ((_normalized_text(alias), factor) for alias, factor in units.items()),
            key=lambda value: (-len(value[0].split()), -len(value[0])),
        )
        unit_expression = "|".join(
            r"\s+".join(re.escape(word) for word in alias.split()) for alias, _ in aliases
        )
        text = self._rule_text(rule, offer)
        match = re.search(rf"(?<![\d.])(\d+(?:\.\d+)?)\s*({unit_expression})(?![a-z])", text)
        if match is None:
            return None
        matched_unit = _normalized_text(match.group(2))
        factor = next(value for alias, value in aliases if alias == matched_unit)
        return self._coerce(Decimal(match.group(1)) * factor, definition)

    def _number_pattern(
        self, rule: JsonObject, definition: JsonObject, offer: NormalizedOffer
    ) -> Any:
        text = self._rule_text(rule, offer)
        group = int(rule.get("group", 1))
        for pattern in rule.get("patterns", []):
            match = re.search(str(pattern), text, re.IGNORECASE)
            if match is not None:
                return self._coerce(match.group(group), definition)
        return None

    def _term_map(self, rule: JsonObject, definition: JsonObject, offer: NormalizedOffer) -> Any:
        text = self._rule_text(rule, offer)
        candidates = [
            (_normalized_text(str(term)), value)
            for value, terms in rule.get("values", {}).items()
            for term in terms
        ]
        candidates.sort(key=lambda item: (-len(item[0].split()), -len(item[0])))
        for term, value in candidates:
            if _contains_pattern(text, term):
                return self._coerce(value, definition)
        default = rule.get("default")
        return self._coerce(default, definition) if default is not None else None

    @staticmethod
    def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
        candidates = sorted(
            (_normalized_text(value) for value in terms),
            key=lambda value: (-len(value.split()), -len(value)),
        )
        return any(_contains_pattern(text, term) for term in candidates)

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
            metrics[output] = self._formulas.evaluate(str(rule["formula"]), values)
        return metrics
