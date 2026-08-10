"""Generic PDP-assisted attribute completion for already-admitted search offers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from rci_analytics.classification import OfferClassifier
from rci_analytics.models import ClassifiedOffer, JsonObject
from rci_analytics.product_pack import ProductPack


def product_context_index(values: list[JsonObject]) -> dict[str, JsonObject]:
    return {
        str(value["canonical_product_id"]): value
        for value in values
        if value.get("canonical_product_id")
    }


def complete_attributes_from_pdp(
    classified: ClassifiedOffer,
    context: JsonObject | None,
    *,
    classifier: OfferClassifier,
    pack: ProductPack,
) -> ClassifiedOffer:
    """Fill unresolved Product Pack attributes from PDP text without changing price.

    The search result remains the admission, price, availability, store, and location
    authority. PDP content is flattened into a classification-only text surface and
    can fill an unresolved attribute; it never overwrites a resolved search attribute.
    """

    if not classified.in_scope or context is None:
        return classified
    pdp_text = _pdp_text(context)
    if not pdp_text:
        return classified
    enriched_offer = replace(
        classified.offer,
        title=pdp_text,
        brand=str(context.get("brand")) if context.get("brand") else classified.offer.brand,
    )
    pdp_classified = classifier.classify(enriched_offer)
    attributes = dict(classified.attributes)
    provenance: JsonObject = {}
    for definition in pack.attributes:
        name = str(definition["name"])
        current = attributes.get(name)
        candidate = pdp_classified.attributes.get(name)
        unknown_values = definition.get("unknown_values", [])
        current_unknown = current is None or current in unknown_values
        candidate_known = candidate is not None and candidate not in unknown_values
        if current_unknown and candidate_known:
            attributes[name] = candidate
            provenance[name] = "pdp"
        elif not current_unknown:
            provenance[name] = "search"
        else:
            provenance[name] = "unresolved"
    attributes["_attribute_provenance"] = provenance
    metrics = dict(classified.metrics)
    for name, value in pdp_classified.metrics.items():
        if metrics.get(name) is None and value is not None:
            metrics[name] = value
    review_reasons = tuple(
        reason
        for reason in classified.review_reasons
        if not (
            reason.startswith("required attribute ")
            and attributes.get(
                reason.removeprefix("required attribute ").removesuffix(" is unresolved")
            )
            is not None
        )
    )
    return replace(
        classified,
        attributes=attributes,
        metrics=metrics,
        review_reasons=review_reasons,
    )


def _pdp_text(context: JsonObject) -> str:
    values: list[str] = []
    for name in ("name", "brand", "description"):
        value = context.get(name)
        if value not in (None, ""):
            values.append(str(value))
    category = context.get("category_path")
    if isinstance(category, list):
        values.extend(str(value) for value in category if value not in (None, ""))
    for name in ("specification", "physical_properties", "variant_configuration"):
        _flatten(context.get(name), values)
    return " | ".join(dict.fromkeys(value.strip() for value in values if value.strip()))


def _flatten(value: Any, output: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            output.append(str(key))
            _flatten(item, output)
    elif isinstance(value, list):
        for item in value:
            _flatten(item, output)
    elif value not in (None, ""):
        output.append(str(value))
