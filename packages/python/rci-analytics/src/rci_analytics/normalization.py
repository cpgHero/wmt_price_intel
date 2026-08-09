"""Canonical normalization for provider dictionaries and supplied CSV extracts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from rci_analytics.models import JsonObject, NormalizedOffer
from rci_locations.normalization import normalize_zipcode

_PRICE_CLEANER = re.compile(r"[^0-9.\-]")


def _first(row: JsonObject, *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _text(row: JsonObject, *names: str) -> str | None:
    value = _first(row, *names)
    return str(value).strip() if value is not None else None


def _decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(_PRICE_CLEANER.sub("", str(value))).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolean(value: Any) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "in stock"}:
        return True
    if normalized in {"0", "false", "no", "n", "out of stock"}:
        return False
    return None


def _datetime_utc(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    parsed: datetime
    try:
        numeric = Decimal(raw)
    except InvalidOperation:
        numeric = None
    try:
        if numeric is not None:
            if not numeric.is_finite():
                return None
            magnitude = abs(numeric)
            if magnitude >= Decimal("1e17"):
                numeric /= Decimal("1e9")
            elif magnitude >= Decimal("1e14"):
                numeric /= Decimal("1e6")
            elif magnitude >= Decimal("1e11"):
                numeric /= Decimal("1e3")
            elif magnitude < Decimal("1e9"):
                return None
            parsed = datetime.fromtimestamp(float(numeric), UTC)
        else:
            iso_value = f"{raw[:-1]}+00:00" if raw.endswith(("Z", "z")) else raw
            parsed = datetime.fromisoformat(iso_value)
            parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return parsed.isoformat().replace("+00:00", "Z")


class RetailerIdentityMap:
    def __init__(self, aliases: dict[str, str]) -> None:
        self._aliases = aliases

    @classmethod
    def from_catalog(cls, path: Path) -> RetailerIdentityMap:
        document = json.loads(path.read_text(encoding="utf-8"))
        aliases: dict[str, str] = {}
        retailers = [
            *document.get("retailers", []),
            *document.get("normalization_only_retailers", []),
        ]
        for retailer in retailers:
            retailer_id = str(retailer["id"])
            values = [
                retailer_id,
                retailer.get("display_name"),
                *retailer.get("api_retailer_aliases", []),
            ]
            for value in values:
                if value:
                    aliases[str(value).strip().casefold()] = retailer_id
        return cls(aliases)

    def normalize(self, value: str) -> str:
        try:
            return self._aliases[value.strip().casefold()]
        except KeyError as exc:
            raise ValueError(f"unknown retailer identity {value!r}") from exc


class CanonicalOfferNormalizer:
    def __init__(self, retailers: RetailerIdentityMap, *, country: str = "USA") -> None:
        self._retailers = retailers
        self._country = country

    def normalize(self, source: JsonObject) -> NormalizedOffer:
        retailer_source = _text(source, "retailer_id", "Retailer", "retailer", "query_retailer")
        if retailer_source is None:
            raise ValueError("offer has no retailer identity")
        retailer_id = self._retailers.normalize(retailer_source)
        title = _text(source, "title", "name", "Product Name")
        if title is None:
            raise ValueError("offer has no product title")
        product_url = _text(source, "product_url", "url", "Url")
        product_id = _text(
            source,
            "retailer_product_id",
            "Retailer Product Id",
            "asin",
            "ASIN",
            "id",
        )
        if product_id is None:
            product_id = hashlib.sha256(f"{title}|{product_url or ''}".encode()).hexdigest()[:24]
        raw_zipcode = _text(
            source,
            "zipcode",
            "Zipcode",
            "pickup_zipcode",
            "shipping_delivery_zipcode",
            "Shipping Delivery Zipcode",
        )
        zipcode = normalize_zipcode(raw_zipcode, self._country) if raw_zipcode else None
        store_number = _text(
            source,
            "store_number",
            "Retailer Store Id",
            "retailer_store_id",
            "pickup_store_id",
        )
        currency = (_text(source, "currency", "Price Currency") or "USD").upper()
        price = _decimal(_first(source, "price", "Price")) if currency == "USD" else None
        identity = "|".join(
            [
                retailer_id,
                product_id,
                zipcode or "",
                store_number or "",
                title,
                str(price) if price is not None else "",
            ]
        )
        return NormalizedOffer(
            offer_id=hashlib.sha256(identity.encode()).hexdigest(),
            retailer_id=retailer_id,
            retailer_product_id=product_id,
            title=title,
            brand=_text(source, "brand", "Brand"),
            price=price,
            currency=currency,
            zipcode=zipcode,
            store_number=store_number,
            latitude=_float(_first(source, "latitude", "Latitude")),
            longitude=_float(_first(source, "longitude", "Longitude")),
            in_stock=_boolean(
                _first(source, "in_stock", "stock_availability", "Stock Availability")
            ),
            product_url=product_url,
            image_url=_text(source, "image_url", "image_primary", "Image Url"),
            collected_at=_datetime_utc(_first(source, "collected_at", "Date", "Time Created")),
            raw=dict(source),
        )

    def normalize_many(self, rows: list[JsonObject]) -> list[NormalizedOffer]:
        normalized: list[NormalizedOffer] = []
        seen_offer_ids: set[str] = set()
        for row in rows:
            try:
                offer = self.normalize(row)
            except ValueError:
                continue
            if offer.offer_id in seen_offer_ids:
                continue
            seen_offer_ids.add(offer.offer_id)
            normalized.append(offer)
        return normalized
