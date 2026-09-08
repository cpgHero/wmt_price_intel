"""Canonical latest-state selection at the retailer product-location grain.

Availability evidence is stateful: a later Search observation supersedes an
earlier observation for the same retailer product and physical/service-area
location.  This module keeps that rule in one category-neutral implementation
so streaming projections cannot retain stale verified availability.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from rci_analytics.models import ClassifiedOffer

ProductLocationKey = tuple[str, str, str, str]
SELLER_POLICY_EXCLUSION_REASON = (
    "known third-party marketplace seller excluded by Retailer Pack policy"
)


def normalized_observed_at(value: str | None) -> str | None:
    """Return an observation timestamp as an explicit RFC 3339 UTC instant."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    return parsed.isoformat().replace("+00:00", "Z")


def observed_at_instant(value: str | None) -> datetime:
    """Return a comparable instant, sorting missing/invalid historical values first."""

    normalized = normalized_observed_at(value)
    if normalized is None:
        return datetime.min.replace(tzinfo=UTC)
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def availability_selection_rank(
    *,
    in_stock: bool | None,
    is_sponsored: bool | None,
) -> int:
    """Return the canonical same-instant availability precedence.

    Organic explicit out-of-stock wins a conflict with organic in-stock so the
    result fails closed.  Organic verified evidence otherwise outranks organic
    unknown, missing sponsorship evidence, and sponsored placement evidence.
    """

    if is_sponsored is False:
        if in_stock is False:
            return 4
        if in_stock is True:
            return 3
        return 2
    if is_sponsored is None:
        return 1
    return 0


def product_location_key(
    *,
    retailer_id: str,
    product_id: str,
    store_number: str | None,
    zipcode: str | None,
) -> ProductLocationKey | None:
    """Return the canonical key, or ``None`` when location identity is absent."""

    if store_number is not None:
        return (retailer_id, product_id, "store", store_number)
    if zipcode is not None:
        return (retailer_id, product_id, "service_area", zipcode)
    return None


@dataclass(frozen=True, slots=True)
class _SelectedState[T]:
    value: T
    observed_at: datetime
    in_stock: bool | None
    is_sponsored: bool | None
    tie_breaker: str

    @property
    def selection_key(self) -> tuple[datetime, int, str]:
        return (
            self.observed_at,
            availability_selection_rank(
                in_stock=self.in_stock,
                is_sponsored=self.is_sponsored,
            ),
            self.tie_breaker,
        )


class LatestProductLocationSelector[T]:
    """Retain one latest state per retailer product-location in bounded memory."""

    def __init__(self) -> None:
        self._selected: dict[ProductLocationKey, _SelectedState[T]] = {}
        self.duplicate_rows = 0
        self.conflicting_availability_keys: set[ProductLocationKey] = set()

    def add(
        self,
        value: T,
        *,
        retailer_id: str,
        product_id: str,
        store_number: str | None,
        zipcode: str | None,
        observed_at: str | None,
        in_stock: bool | None,
        is_sponsored: bool | None,
        tie_breaker: str,
    ) -> bool:
        """Add a candidate and return whether it became the selected state."""

        key = product_location_key(
            retailer_id=retailer_id,
            product_id=product_id,
            store_number=store_number,
            zipcode=zipcode,
        )
        if key is None:
            return False
        candidate = _SelectedState(
            value=value,
            observed_at=observed_at_instant(observed_at),
            in_stock=in_stock,
            is_sponsored=is_sponsored,
            tie_breaker=tie_breaker,
        )
        current = self._selected.get(key)
        if current is None:
            self._selected[key] = candidate
            return True

        self.duplicate_rows += 1
        if (
            current.observed_at == candidate.observed_at
            and current.is_sponsored is False
            and candidate.is_sponsored is False
            and {current.in_stock, candidate.in_stock} == {True, False}
        ):
            self.conflicting_availability_keys.add(key)
        if candidate.selection_key > current.selection_key:
            self._selected[key] = candidate
            return True
        return False

    def get(self, key: ProductLocationKey) -> T | None:
        selected = self._selected.get(key)
        return selected.value if selected is not None else None

    def items(self) -> tuple[tuple[ProductLocationKey, T], ...]:
        return tuple((key, self._selected[key].value) for key in sorted(self._selected))

    def values(self) -> tuple[T, ...]:
        return tuple(value for _key, value in self.items())

    def __len__(self) -> int:
        return len(self._selected)


def add_classified_offer(
    selector: LatestProductLocationSelector[ClassifiedOffer],
    item: ClassifiedOffer,
) -> bool:
    """Add a classified offer using the canonical product-location fields."""

    offer = item.offer
    return selector.add(
        item,
        retailer_id=offer.retailer_id,
        product_id=offer.retailer_product_id,
        store_number=offer.store_number,
        zipcode=offer.zipcode,
        observed_at=offer.collected_at,
        in_stock=offer.in_stock,
        is_sponsored=offer.is_sponsored,
        tie_breaker=offer.offer_id,
    )


def is_product_location_state(item: ClassifiedOffer) -> bool:
    """Return whether a classified row can establish or retract location state.

    Some Product Packs apply availability or positive-price policy after all
    category exclusions. Rows that fail only those policies remain authoritative
    availability states and must retract older verified evidence. Other
    out-of-scope rows remain excluded.
    """

    return bool(
        item.in_scope
        or (item.scope_reason == "explicitly out of stock" and item.offer.in_stock is False)
        or (
            item.scope_reason == "positive USD price is required"
            and (item.offer.price is None or item.offer.price <= 0)
        )
        or is_seller_policy_exclusion(item)
    )


def is_seller_policy_exclusion(item: ClassifiedOffer) -> bool:
    """Return whether PDP seller governance explicitly rejected this listing."""

    return bool(not item.in_scope and item.scope_reason == SELLER_POLICY_EXCLUSION_REASON)


def latest_classified_offers(
    items: Iterable[ClassifiedOffer],
    *,
    in_scope_only: bool = True,
) -> list[ClassifiedOffer]:
    """Select latest classified states with the canonical streaming selector."""

    selector: LatestProductLocationSelector[ClassifiedOffer] = LatestProductLocationSelector()
    for item in items:
        if in_scope_only and not is_product_location_state(item):
            continue
        add_classified_offer(selector, item)
    return list(selector.values())
