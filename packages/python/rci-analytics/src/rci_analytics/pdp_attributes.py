"""Generic PDP-assisted attribute completion for already-admitted search offers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from rci_analytics.classification import OfferClassifier
from rci_analytics.models import ClassifiedOffer, JsonObject
from rci_analytics.product_pack import ProductPack
from rci_retailer_packs import GovernedSellerResolver


def product_context_index(values: list[JsonObject]) -> dict[str, JsonObject]:
    """Index only records backed by a normalized Product Details snapshot."""

    return {
        str(value["canonical_product_id"]): value
        for value in values
        if value.get("canonical_product_id") and value.get("role") == "PDP-enriched reference"
    }


def complete_attributes_from_pdp(
    classified: ClassifiedOffer,
    context: JsonObject | None,
    *,
    classifier: OfferClassifier,
    pack: ProductPack,
    seller_resolver: GovernedSellerResolver | None = None,
) -> ClassifiedOffer:
    """Fill unresolved Product Pack attributes from PDP text without changing price.

    The search result remains the admission, price, availability, store, and location
    authority. PDP content is flattened into a classification-only text surface and
    can fill an unresolved attribute; it never overwrites explicit Search, Product Pack
    override, or configured-constant evidence. Inferred defaults are not evidence.
    """

    if not classified.in_scope:
        return classified
    attributes = dict(classified.attributes)
    provenance = (
        dict(attributes.get("_attribute_provenance", {}))
        if isinstance(attributes.get("_attribute_provenance"), dict)
        else {}
    )
    metrics = dict(classified.metrics)
    if context is not None:
        attributes["_pdp_evidence"] = _pdp_evidence(context)
        pdp_text = _pdp_text(context)
        if pdp_text:
            enriched_offer = replace(
                classified.offer,
                title=pdp_text,
                brand=(
                    str(context.get("brand")) if context.get("brand") else classified.offer.brand
                ),
                raw=_pdp_classification_raw(classified.offer.raw, context),
            )
            pdp_classified = classifier.classify(enriched_offer)
            pdp_provenance = (
                dict(pdp_classified.attributes.get("_attribute_provenance", {}))
                if isinstance(pdp_classified.attributes.get("_attribute_provenance"), dict)
                else {}
            )
            for definition in pack.attributes:
                name = str(definition["name"])
                current = attributes.get(name)
                candidate = pdp_classified.attributes.get(name)
                unknown_values = definition.get("unknown_values", [])
                current_source = str(provenance.get(name) or "unresolved")
                candidate_source = str(pdp_provenance.get(name) or "unresolved")
                current_unknown = (
                    current is None
                    or current in unknown_values
                    or current_source in {"unresolved", "product_pack_default"}
                )
                candidate_known = (
                    candidate is not None
                    and candidate not in unknown_values
                    and candidate_source not in {"unresolved", "product_pack_default"}
                )
                if current_unknown and candidate_known:
                    attributes[name] = candidate
                    provenance[name] = "pdp"
                elif not current_unknown:
                    provenance[name] = current_source
                else:
                    provenance[name] = "unresolved"
            current_brand_governance = attributes.get("_brand_governance")
            pdp_brand_governance = pdp_classified.attributes.get("_brand_governance")
            current_brand_resolved = (
                isinstance(current_brand_governance, dict)
                and current_brand_governance.get("status") == "resolved"
            )
            pdp_brand_resolved = (
                isinstance(pdp_brand_governance, dict)
                and pdp_brand_governance.get("status") == "resolved"
            )
            if not current_brand_resolved and pdp_brand_resolved:
                # PDP may complete product identity, but not Search price or placement.
                assert isinstance(pdp_brand_governance, dict)
                attributes["_brand_governance"] = dict(pdp_brand_governance)
                pdp_brand = pdp_classified.attributes.get("brand")
                if pdp_brand:
                    attributes["brand"] = pdp_brand
                    provenance["brand"] = "pdp"
            for name, value in pdp_classified.metrics.items():
                if metrics.get(name) is None and value is not None:
                    metrics[name] = value
    attributes["_attribute_provenance"] = provenance
    seller_decision = None
    if seller_resolver is not None:
        seller_decision = seller_resolver.resolve(
            classified.offer.retailer_id,
            context.get("seller") if context is not None else None,
        )
        attributes["_seller_governance"] = seller_decision.to_record()
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
        in_scope=(classified.in_scope and (seller_decision is None or seller_decision.eligible)),
        scope_reason=(
            "known third-party marketplace seller excluded by Retailer Pack policy"
            if seller_decision is not None and not seller_decision.eligible
            else classified.scope_reason
        ),
        attributes=attributes,
        metrics=(metrics if seller_decision is None or seller_decision.eligible else {}),
        review_reasons=review_reasons,
    )


def _pdp_evidence(context: JsonObject) -> JsonObject:
    """Retain bounded identity evidence needed for matching certification."""

    fields = (
        "name",
        "brand",
        "seller",
        "description",
        "category_path",
        "identifiers",
        "specification",
        "physical_properties",
        "variant_configuration",
        "item_condition",
        "image_url",
        "image_urls",
        "url",
        "pdp_source_field_inventory",
        "pdp_unmapped_source_fields",
    )
    return {name: context.get(name) for name in fields if context.get(name) not in (None, "")}


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


def _pdp_classification_raw(current: JsonObject, context: JsonObject) -> JsonObject:
    """Expose structured PDP fields to generic Product Pack ``raw.*`` extractors."""

    merged = dict(current)
    for name in ("specification", "physical_properties", "variant_configuration"):
        value = context.get(name)
        if isinstance(value, dict):
            merged.update({str(key): item for key, item in value.items()})
    return merged


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
