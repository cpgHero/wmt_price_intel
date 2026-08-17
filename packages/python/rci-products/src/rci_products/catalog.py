"""Schema-backed MetricsCart Product Details endpoint catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from rci_contracts import validate_instance
from rci_products.models import ProductDetailEndpoint


class ProductDetailCatalog:
    def __init__(self, endpoints: dict[str, ProductDetailEndpoint]) -> None:
        self._endpoints = endpoints

    @classmethod
    def from_path(cls, repository_root: Path, path: Path | None = None) -> ProductDetailCatalog:
        catalog_path = path or repository_root / "config" / "product-detail-catalog.json"
        document = json.loads(catalog_path.read_text(encoding="utf-8"))
        validate_instance(
            repository_root,
            "product-detail-catalog.schema.json",
            document,
            label=str(catalog_path),
        )
        endpoints: dict[str, ProductDetailEndpoint] = {}
        for value in document["endpoints"]:
            endpoint = ProductDetailEndpoint(
                retailer_id=str(value["retailer_id"]),
                provider_retailer=str(value["provider_retailer"]),
                domain=str(value["domain"]),
                endpoint_id=str(value["endpoint_id"]),
                method=str(value["method"]).upper(),
                path=str(value["path"]),
                credits_per_successful_page=int(value["credits_per_successful_page"]),
                paid_calls_enabled=bool(value["paid_calls_enabled"]),
                required_params=tuple(str(item) for item in value["required_params"]),
                supported_params=tuple(str(item) for item in value["supported_params"]),
                contract_version=str(value.get("contract_version", "1.0.0")),
                default_params=tuple(
                    sorted(
                        (str(name), str(parameter_value))
                        for name, parameter_value in value.get("default_params", {}).items()
                    )
                ),
                identity_param=(
                    cast(
                        Literal["product_id", "url"],
                        str(value["identity_param"]),
                    )
                    if value.get("identity_param")
                    else None
                ),
                product_id_left_pad_width=(
                    int(value["product_id_left_pad_width"])
                    if value.get("product_id_left_pad_width") is not None
                    else None
                ),
            )
            if endpoint.retailer_id in endpoints:
                raise ValueError(f"duplicate Product Details endpoint {endpoint.retailer_id!r}")
            endpoints[endpoint.retailer_id] = endpoint
        return cls(endpoints)

    def get(self, retailer_id: str) -> ProductDetailEndpoint:
        try:
            return self._endpoints[retailer_id]
        except KeyError as exc:
            raise ValueError(f"no Product Details endpoint for retailer {retailer_id!r}") from exc

    def enabled_v1(self) -> tuple[ProductDetailEndpoint, ...]:
        return tuple(
            self._endpoints[retailer_id]
            for retailer_id in ("walmart_us", "aldi_us", "amazon_us_same_day")
        )
