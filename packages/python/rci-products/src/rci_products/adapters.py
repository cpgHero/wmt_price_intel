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

_MAPPED_SOURCE_FIELDS = frozenset(
    {
        "brand",
        "category",
        "category_path",
        "description_full",
        "description_short",
        "enhanced_content_raw",
        "extras",
        "fulfiled_by_retailer",
        "fulfilled_by_retailer",
        "has_360_images",
        "has_enhanced_content",
        "image_primary",
        "images",
        "item_condition",
        "model_number",
        "monthly_sales_volume",
        "name",
        "offers",
        "physical_properties",
        "pickup_address",
        "pickup_available",
        "pickup_extras",
        "pickup_store_id",
        "pickup_zipcode",
        "price",
        "price_currency",
        "price_discount_percent",
        "price_discounted",
        "price_is_discounted",
        "price_regular",
        "product_aspects",
        "product_identifiers",
        "rating",
        "rating_count",
        "related_products_also_viewed",
        "related_products_bought_together",
        "related_products_similar",
        "related_products_sponsored",
        "retailer",
        "retailer_product_id",
        "retailer_ranks",
        "retailer_review_summary",
        "retailer_store_id",
        "return_extras",
        "returnable",
        "returnable_in",
        "reviews_count",
        "reviews_summary",
        "seller",
        "shipping_cost",
        "shipping_delivery_address",
        "shipping_delivery_zipcode",
        "shipping_expected_delivery_date",
        "shipping_extras",
        "shipping_type",
        "source",
        "specification",
        "stock_availability",
        "stock_quantity",
        "url",
        "variant_configuration",
        "variants",
        "video_count",
        "videos",
        "weekly_sales_volume",
        "zipcode",
    }
)


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


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


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
        if not self.endpoint.paid_calls_enabled:
            raise ValueError(
                "Product Details endpoint is blocked pending controlled contract preflight"
            )
        supplied = {**self.endpoint.defaults(), **context.parameters()}
        if not context.product_id and not context.url:
            raise ValueError("Product Details requires a product_id or url")
        if not any(
            supplied.get(name)
            for name in ("product_id", "url")
            if name in self.endpoint.supported_params
        ):
            raise ValueError("Product Details requires an endpoint-supported product_id or url")
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
        commerce = {
            "item_condition": _text(payload.get("item_condition")),
            "price_regular": _number(payload.get("price_regular")),
            "price_discounted": _number(payload.get("price_discounted")),
            "price_discount_percent": _number(payload.get("price_discount_percent")),
            "price_is_discounted": _boolean(payload.get("price_is_discounted")),
            "offers": _list(payload.get("offers")),
        }
        fulfillment = {
            "fulfilled_by_retailer": (
                _boolean(payload.get("fulfilled_by_retailer"))
                if payload.get("fulfilled_by_retailer") is not None
                else _boolean(payload.get("fulfiled_by_retailer"))
            ),
            "retailer_store_id": _text(payload.get("retailer_store_id")),
            "stock_available": _boolean(payload.get("stock_availability")),
            "stock_quantity": _number(payload.get("stock_quantity")),
            "pickup_available": _boolean(payload.get("pickup_available")),
            "pickup_store_id": _text(payload.get("pickup_store_id")),
            "pickup_zipcode": _text(payload.get("pickup_zipcode")),
            "pickup_address": _text(payload.get("pickup_address")),
            "pickup_extras": _object(payload.get("pickup_extras")),
            "shipping_type": _text(payload.get("shipping_type")),
            "shipping_expected_delivery_date": _text(
                payload.get("shipping_expected_delivery_date")
            ),
            "shipping_delivery_zipcode": _text(payload.get("shipping_delivery_zipcode")),
            "shipping_delivery_address": _text(payload.get("shipping_delivery_address")),
            "shipping_cost": _number(payload.get("shipping_cost")),
            "shipping_extras": _object(payload.get("shipping_extras")),
            "returnable": _boolean(payload.get("returnable")),
            "returnable_in": _number(payload.get("returnable_in")),
            "return_extras": _object(payload.get("return_extras")),
        }
        reviews = {
            "rating": _number(payload.get("rating")),
            "rating_count": _number(payload.get("rating_count")),
            "reviews_count": _number(payload.get("reviews_count")),
            "reviews_summary": _object(payload.get("reviews_summary")),
            "retailer_review_summary": payload.get("retailer_review_summary"),
            "product_aspects": _list(payload.get("product_aspects")),
        }
        demand = {
            "monthly_sales_volume": _number(payload.get("monthly_sales_volume")),
            "weekly_sales_volume": _number(payload.get("weekly_sales_volume")),
            "retailer_ranks": _object(payload.get("retailer_ranks")),
        }
        content = {
            "model_number": _text(payload.get("model_number")),
            "video_count": _number(payload.get("video_count")),
            "has_360_images": _boolean(payload.get("has_360_images")),
            "has_enhanced_content": _boolean(payload.get("has_enhanced_content")),
            "enhanced_content_present": payload.get("enhanced_content_raw") is not None,
        }
        relationships = {
            "also_viewed": _list(payload.get("related_products_also_viewed")),
            "bought_together": _list(payload.get("related_products_bought_together")),
            "similar": _list(payload.get("related_products_similar")),
            "sponsored": _list(payload.get("related_products_sponsored")),
            "variants": _list(payload.get("variants")),
        }
        source_context = {
            "zipcode": _text(payload.get("zipcode")),
            "retailer": _text(payload.get("retailer")),
            "source": _text(payload.get("source")),
        }
        source_fields = tuple(sorted(str(name) for name in payload))
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
            commerce=commerce,
            fulfillment=fulfillment,
            reviews=reviews,
            demand=demand,
            content=content,
            relationships=relationships,
            source_context=source_context,
            source_field_inventory=source_fields,
            unmapped_source_fields=tuple(
                name for name in source_fields if name not in _MAPPED_SOURCE_FIELDS
            ),
            extras=extras,
        )
