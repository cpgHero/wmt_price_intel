"""Cost-aware Product Details planning from analysis-admitted observations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from rci_products.models import JsonObject, ProductDetailRequestContext


@dataclass(frozen=True, slots=True)
class ProductDetailCandidate:
    """One representative PDP request for an analysis-admitted product/price state."""

    retailer_id: str
    retailer_product_id: str
    context: ProductDetailRequestContext
    observed_price: Decimal | None
    reason: Literal["product_reference", "location_price_variant"]
    source_offer_id: str


def _price(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed.normalize()


def _text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _rank(observation: JsonObject) -> tuple[object, ...]:
    """Choose a stable, request-complete representative without inventing a location."""

    zipcode = _text(observation.get("zipcode"))
    store = _text(observation.get("store_number") or observation.get("store"))
    fulfillment = _text(observation.get("fulfillment_type"))
    completeness = sum(value is not None for value in (zipcode, store, fulfillment))
    return (
        -completeness,
        zipcode or "",
        store or "",
        fulfillment or "",
        _text(observation.get("offer_id")) or "",
    )


def plan_product_detail_candidates(
    observations: Iterable[JsonObject],
    *,
    analysis_offer_ids: set[str],
) -> list[ProductDetailCandidate]:
    """Plan PDP calls only for offers admitted into a completed analysis.

    Repeated observations of the same retailer product produce one request. When that
    product has distinct observed prices across locations, one representative request is
    retained for each price state so PDP evidence can explain the location variance without
    fetching the product at every store.
    """

    grouped: dict[tuple[str, str], list[JsonObject]] = defaultdict(list)
    for observation in observations:
        offer_id = _text(observation.get("offer_id"))
        retailer_id = _text(observation.get("retailer_id"))
        product_id = _text(observation.get("retailer_product_id"))
        if (
            offer_id is None
            or offer_id not in analysis_offer_ids
            or retailer_id is None
            or product_id is None
        ):
            continue
        grouped[(retailer_id, product_id)].append(dict(observation))

    candidates: list[ProductDetailCandidate] = []
    for (retailer_id, product_id), product_rows in sorted(grouped.items()):
        by_price: dict[Decimal | None, list[JsonObject]] = defaultdict(list)
        for observation in product_rows:
            by_price[_price(observation.get("price"))].append(observation)
        known_prices = sorted(price for price in by_price if price is not None)
        price_variance = len(known_prices) > 1
        planned_groups = (
            [(price, by_price[price]) for price in known_prices]
            if price_variance
            else (
                [(known_prices[0], by_price[known_prices[0]])]
                if known_prices
                else [(None, product_rows)]
            )
        )
        for observed_price, price_rows in planned_groups:
            representative = min(price_rows, key=_rank)
            offer_id = str(representative["offer_id"])
            candidates.append(
                ProductDetailCandidate(
                    retailer_id=retailer_id,
                    retailer_product_id=product_id,
                    context=ProductDetailRequestContext(
                        product_id=product_id,
                        zipcode=_text(representative.get("zipcode")),
                        store=_text(
                            representative.get("store_number") or representative.get("store")
                        ),
                        fulfillment_type=_text(representative.get("fulfillment_type")),
                        url=_text(representative.get("product_url") or representative.get("url")),
                    ),
                    observed_price=observed_price,
                    reason=("location_price_variant" if price_variance else "product_reference"),
                    source_offer_id=offer_id,
                )
            )
    return candidates
