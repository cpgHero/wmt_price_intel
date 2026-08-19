"""Unmatched retailer assortment architecture across benchmark-defined price rungs."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import mean, median
from typing import Literal

from rci_analytics.models import JsonObject
from rci_analytics.product_location import ProductLocationObservation

PriceArchitectureMode = Literal["benchmark_anchored", "fixed_range"]


@dataclass(frozen=True, slots=True)
class PriceArchitectureRetailerInput:
    retailer_id: str
    retailer_name: str
    location_dimension: Literal["store", "service_area"]
    eligible_scope_keys: frozenset[str]
    observations: tuple[ProductLocationObservation, ...]
    population_checksum: str


def _round(value: float | int | None, places: int = 4) -> float | None:
    return round(float(value), places) if value is not None else None


def _product_rows(retailer: PriceArchitectureRetailerInput) -> list[JsonObject]:
    grouped: dict[str, list[ProductLocationObservation]] = defaultdict(list)
    for observation in retailer.observations:
        grouped[observation.product_id].append(observation)
    products: list[JsonObject] = []
    for product_id, observations in grouped.items():
        identity = observations[0]
        prices = [row.package_price for row in observations]
        products.append(
            {
                "product_id": product_id,
                "name": identity.product_name,
                "brand": identity.brand,
                "brand_type": identity.brand_type,
                "image_url": identity.image_url,
                "url": identity.product_url,
                "median_price": _round(median(prices)),
                "minimum_price": _round(min(prices)),
                "maximum_price": _round(max(prices)),
                "observed_locations": len({row.location.scope_key for row in observations}),
                "location_keys": frozenset(row.location.scope_key for row in observations),
            }
        )
    products.sort(
        key=lambda row: (
            float(row["median_price"]),
            str(row["name"]).casefold(),
            str(row["product_id"]),
        )
    )
    return products


def _anchor_bands(anchor_products: list[JsonObject]) -> list[JsonObject]:
    price_points = sorted({float(row["median_price"]) for row in anchor_products})
    bands: list[JsonObject] = []
    for index, price in enumerate(price_points):
        lower = (price_points[index - 1] + price) / 2 if index else None
        upper = (price + price_points[index + 1]) / 2 if index + 1 < len(price_points) else None
        bands.append(
            {
                "id": f"anchor-{index + 1}",
                "anchor_price": _round(price),
                "lower_bound": _round(lower),
                "upper_bound": _round(upper),
            }
        )
    return bands


def _fixed_bands(products: Iterable[JsonObject], increment: float) -> list[JsonObject]:
    maximum = max((float(row["median_price"]) for row in products), default=0)
    top_index = max(0, math.floor(maximum / increment))
    return [
        {
            "id": f"fixed-{index + 1}",
            "anchor_price": None,
            "lower_bound": _round(index * increment),
            "upper_bound": _round((index + 1) * increment) if index < top_index else None,
        }
        for index in range(top_index + 1)
    ]


def _band_for_price(bands: list[JsonObject], price: float) -> JsonObject:
    for band in bands:
        lower = band["lower_bound"]
        upper = band["upper_bound"]
        if (lower is None or price >= float(lower)) and (upper is None or price < float(upper)):
            return band
    raise ValueError(f"price {price} does not fall into a configured price rung")


def _band_label(band: JsonObject) -> str:
    lower = band["lower_bound"]
    upper = band["upper_bound"]
    if lower is None and upper is not None:
        return f"Under ${float(upper):.2f}"
    if lower is not None and upper is None:
        return f"${float(lower):.2f}+"
    assert lower is not None and upper is not None
    return f"${float(lower):.2f} to ${float(upper):.2f}"


class PriceArchitectureMatrixProjector:
    """Place retailer SKUs into benchmark-defined bands without matching products."""

    def build(
        self,
        *,
        analysis_id: str,
        generated_at: str,
        product_pack: JsonObject,
        anchor_retailer_id: str,
        retailers: Iterable[PriceArchitectureRetailerInput],
        mode: PriceArchitectureMode = "benchmark_anchored",
        fixed_increment: float = 0.5,
        brand_type: str = "all",
        state: str | None = None,
        city: str | None = None,
        zipcode: str | None = None,
        unavailable_retailers: Iterable[JsonObject] = (),
    ) -> JsonObject:
        if mode == "fixed_range" and fixed_increment not in {0.5, 1.0}:
            raise ValueError("fixed price-rung increment must be 0.50 or 1.00")
        inputs = list(retailers)
        anchor = next(
            (row for row in inputs if row.retailer_id == anchor_retailer_id),
            None,
        )
        if anchor is None:
            raise ValueError("benchmark retailer evidence is required to define price rungs")
        products_by_retailer = {row.retailer_id: _product_rows(row) for row in inputs}
        anchor_products = products_by_retailer[anchor_retailer_id]
        if not anchor_products:
            raise ValueError("benchmark retailer has no eligible positive-price products")
        all_products = [
            product for products in products_by_retailer.values() for product in products
        ]
        bands = (
            _anchor_bands(anchor_products)
            if mode == "benchmark_anchored"
            else _fixed_bands(all_products, fixed_increment)
        )
        assigned: dict[tuple[str, str], list[JsonObject]] = defaultdict(list)
        for retailer_id, products in products_by_retailer.items():
            for product in products:
                band = _band_for_price(bands, float(product["median_price"]))
                assigned[(str(band["id"]), retailer_id)].append(product)

        retailer_rows: list[JsonObject] = []
        for retailer in inputs:
            products = products_by_retailer[retailer.retailer_id]
            observed_locations = len({row.location.scope_key for row in retailer.observations})
            retailer_rows.append(
                {
                    "id": retailer.retailer_id,
                    "name": retailer.retailer_name,
                    "status": "available",
                    "location_dimension": retailer.location_dimension,
                    "sku_count": len(products),
                    "eligible_locations": len(retailer.eligible_scope_keys),
                    "observed_locations": observed_locations,
                    "population_checksum": retailer.population_checksum,
                    "reason": None,
                }
            )
        retailer_rows.extend(dict(row) for row in unavailable_retailers)
        retailer_rows.sort(
            key=lambda row: (
                0 if row["id"] == anchor_retailer_id else 1,
                str(row["name"]).casefold(),
            )
        )

        rung_rows: list[JsonObject] = []
        competitor_ids = {
            str(row["id"])
            for row in retailer_rows
            if row["id"] != anchor_retailer_id and row["status"] == "available"
        }
        for rank, band in enumerate(reversed(bands), start=1):
            band_id = str(band["id"])
            cells: list[JsonObject] = []
            for retailer in inputs:
                products = assigned.get((band_id, retailer.retailer_id), [])
                retailer_total = len(products_by_retailer[retailer.retailer_id])
                location_keys = {
                    location_key
                    for product in products
                    for location_key in product["location_keys"]
                }
                finite_width = (
                    float(band["upper_bound"]) - float(band["lower_bound"])
                    if band["upper_bound"] is not None and band["lower_bound"] is not None
                    else None
                )
                contract_products = [
                    {key: value for key, value in product.items() if key != "location_keys"}
                    for product in products
                ]
                cells.append(
                    {
                        "retailer_id": retailer.retailer_id,
                        "sku_count": len(products),
                        "assortment_share": _round(len(products) / retailer_total)
                        if retailer_total
                        else None,
                        "store_coverage": _round(
                            len(location_keys) / len(retailer.eligible_scope_keys)
                        )
                        if retailer.eligible_scope_keys
                        else None,
                        "average_price": _round(
                            mean(float(product["median_price"]) for product in products)
                        )
                        if products
                        else None,
                        "price_density": _round(len(products) / finite_width)
                        if products and finite_width
                        else None,
                        "products": contract_products,
                    }
                )
            anchor_cell = next(row for row in cells if row["retailer_id"] == anchor_retailer_id)
            competitor_skus = sum(
                int(row["sku_count"]) for row in cells if row["retailer_id"] in competitor_ids
            )
            rung_rows.append(
                {
                    **band,
                    "rank": rank,
                    "label": _band_label(band),
                    "anchor_products": anchor_cell["products"],
                    "competitor_sku_count": competitor_skus,
                    "cells": cells,
                }
            )

        crowded = max(rung_rows, key=lambda row: int(row["competitor_sku_count"]))
        whitespace = [row for row in rung_rows if int(row["competitor_sku_count"]) == 0]
        return {
            "schema_version": "1.0.0",
            "analysis_id": analysis_id,
            "generated_at": generated_at,
            "product_pack": product_pack,
            "source": {
                "authority": "Search",
                "price_grain": (
                    "retailer product x median positive shelf price across observed locations"
                ),
                "assignment_rule": "price only; no product-match relationship is used",
                "anchor_rule": (
                    "midpoints between adjacent distinct benchmark SKU median prices"
                    if mode == "benchmark_anchored"
                    else f"fixed ${fixed_increment:.2f} package-price bands"
                ),
            },
            "filters": {
                "anchor_retailer_id": anchor_retailer_id,
                "mode": mode,
                "fixed_increment": fixed_increment,
                "brand_type": brand_type,
                "state": state,
                "city": city,
                "zipcode": zipcode,
            },
            "summary": {
                "anchor_price_points": len(
                    {float(product["median_price"]) for product in anchor_products}
                ),
                "rung_count": len(bands),
                "anchor_skus": len(anchor_products),
                "competitor_skus": sum(
                    len(products)
                    for retailer_id, products in products_by_retailer.items()
                    if retailer_id != anchor_retailer_id
                ),
                "most_crowded_rung_id": crowded["id"],
                "whitespace_rung_count": len(whitespace),
            },
            "retailers": retailer_rows,
            "rungs": rung_rows,
        }
