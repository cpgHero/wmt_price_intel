"""Catalog-driven MetricsCart Product Details request and response adapters."""

from __future__ import annotations

from collections.abc import Mapping

from rci_products.models import (
    JsonObject,
    NormalizedProductDetail,
    ProductDetailEndpoint,
    ProductDetailRequestContext,
)
from rci_providers.models import ProviderRequest


def _text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _number(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _boolean(value: object) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "in stock"}:
        return True
    if normalized in {"0", "false", "no", "out of stock"}:
        return False
    return None


def _object(value: object) -> JsonObject:
    return dict(value) if isinstance(value, Mapping) else {}


def _category_path(payload: JsonObject) -> str | None:
    direct = _text(payload.get("category_path"))
    if direct is not None:
        return direct
    candidates = payload.get("category")
    if not isinstance(candidates, list):
        candidates = _object(payload.get("extras")).get("category")
    if not isinstance(candidates, list):
        return None
    names = [
        name
        for item in candidates
        if isinstance(item, Mapping) and (name := _text(item.get("name"))) is not None
    ]
    return " > ".join(names) or None


class MetricsCartProductDetailAdapter:
    def __init__(self, endpoint: ProductDetailEndpoint) -> None:
        self.endpoint = endpoint
        self.retailer_id = endpoint.retailer_id

    def build_request(self, context: ProductDetailRequestContext) -> ProviderRequest:
        supplied = context.parameters()
        if not context.product_id and not context.url:
            raise ValueError("Product Details requires a product_id or url")
        unsupported = set(supplied) - set(self.endpoint.supported_params)
        if unsupported:
            raise ValueError(
                f"unsupported Product Details parameters: {', '.join(sorted(unsupported))}"
            )
        missing = [name for name in self.endpoint.required_params if not supplied.get(name)]
        if missing:
            raise ValueError(
                f"missing required Product Details parameters: {', '.join(sorted(missing))}"
            )
        return ProviderRequest(
            method=self.endpoint.method,
            path=self.endpoint.path,
            params={
                name: supplied[name] for name in self.endpoint.supported_params if name in supplied
            },
        )

    def normalize(
        self,
        payload: JsonObject,
        context: ProductDetailRequestContext,
    ) -> NormalizedProductDetail:
        identifiers = {
            str(key): text
            for key, value in _object(payload.get("product_identifiers")).items()
            if (text := _text(value)) is not None
        }
        retailer_product_id = (
            _text(payload.get("retailer_product_id"))
            or identifiers.get("product_id")
            or identifiers.get("item_id")
            or identifiers.get("asin")
            or context.product_id
        )
        name = _text(payload.get("name"))
        if not retailer_product_id:
            raise ValueError("Product Details response has no retailer product identifier")
        if name is None:
            raise ValueError("Product Details response has no product name")
        identifiers.setdefault("retailer_product_id", retailer_product_id)
        identifiers.setdefault("product_id", context.product_id)
        image_primary = _text(payload.get("image_primary"))
        images = (
            tuple(
                image for value in payload.get("images", []) if (image := _text(value)) is not None
            )
            if isinstance(payload.get("images"), list)
            else ()
        )
        videos = tuple(payload.get("videos", [])) if isinstance(payload.get("videos"), list) else ()
        extras = {
            **_object(payload.get("extras")),
            "retailer_store_id": _text(payload.get("retailer_store_id")),
            "source_retailer": _text(payload.get("retailer")),
            "source": _text(payload.get("source")),
        }
        return NormalizedProductDetail(
            retailer_product_id=retailer_product_id,
            name=name,
            brand=_text(payload.get("brand")),
            seller=_text(payload.get("seller")),
            url=_text(payload.get("url")),
            description_short=_text(payload.get("description_short")),
            description_full=_text(payload.get("description_full")),
            category_path=_category_path(payload),
            identifiers=identifiers,
            specification=_object(payload.get("specification")),
            physical_properties=_object(payload.get("physical_properties")),
            variant_configuration=_object(payload.get("variant_configuration")),
            price=_number(payload.get("price")),
            price_currency=_text(payload.get("price_currency")),
            stock_available=_boolean(payload.get("stock_availability")),
            pickup_available=_boolean(payload.get("pickup_available")),
            stock_quantity=_number(payload.get("stock_quantity")),
            pickup_store_id=_text(payload.get("pickup_store_id")),
            shipping_type=_text(payload.get("shipping_type")),
            image_primary=image_primary,
            images=images or ((image_primary,) if image_primary else ()),
            videos=videos,
            extras=extras,
        )
