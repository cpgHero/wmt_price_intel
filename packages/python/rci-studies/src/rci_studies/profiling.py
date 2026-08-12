"""Deterministic product population profiling before Product Pack certification."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from rci_retailer_packs import GovernedBrandResolver
from rci_studies.models import (
    DiscoveryObservation,
    DiscoveryProduct,
    DiscoveryProfile,
    JsonObject,
)


def canonical_checksum(value: JsonObject) -> str:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(rendered.encode()).hexdigest()


def _terms(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(sorted({str(value).strip().casefold() for value in values if str(value).strip()}))


def initial_query_plan(
    category_context: str,
    *,
    known_inclusions: Iterable[str] = (),
    known_exclusions: Iterable[str] = (),
) -> JsonObject:
    """Create a conservative, editable starting point without spending AI tokens."""

    inclusions = [value.strip() for value in known_inclusions if value.strip()]
    keyword = inclusions[0] if inclusions else category_context.strip().split(".", 1)[0].strip()
    keyword = " ".join(keyword.split())[:200]
    target_terms: set[str] = {*(value.casefold() for value in inclusions), keyword.casefold()}
    for value in [*inclusions, keyword]:
        token = value.casefold().split()[-1]
        target_terms.add(token)
        if token.endswith("ies") and len(token) > 3:
            target_terms.add(f"{token[:-3]}y")
        elif token.endswith("s") and len(token) > 3:
            target_terms.add(token[:-1])
        else:
            target_terms.add(f"{token}s")
    return {
        "keyword": keyword,
        "target_terms": sorted(target_terms),
        "exclusion_terms": sorted(
            {value.strip().casefold() for value in known_exclusions if value.strip()}
        ),
        "alternate_queries": [],
        "source": "deterministic",
        "rationale": "Initial query created from the administrator's category context.",
        "revision": 1,
    }


def _rank(observation: DiscoveryObservation) -> tuple[object, ...]:
    completeness = sum(
        value is not None
        for value in (
            observation.zipcode,
            observation.store_number,
            observation.url,
            observation.image_url,
        )
    )
    return (
        -completeness,
        observation.zipcode or "",
        observation.store_number or "",
        observation.title.casefold(),
    )


def _context(observation: DiscoveryObservation) -> JsonObject:
    return {
        "zipcode": observation.zipcode,
        "store_number": observation.store_number,
        "fulfillment_type": observation.fulfillment_type,
        "observed_price": (float(observation.price) if observation.price is not None else None),
        "source_artifact_id": observation.source_artifact_id,
    }


def profile_products(
    observations: Iterable[DiscoveryObservation],
    *,
    query_plan: JsonObject,
    brand_resolver: GovernedBrandResolver,
) -> DiscoveryProfile:
    """Deduplicate Search observations and retain one PDP context per price state."""

    rows = list(observations)
    grouped: dict[tuple[str, str], list[DiscoveryObservation]] = defaultdict(list)
    for row in rows:
        grouped[(row.retailer_id, row.retailer_product_id)].append(row)
    targets = _terms(query_plan.get("target_terms"))
    exclusions = _terms(query_plan.get("exclusion_terms"))
    products: list[DiscoveryProduct] = []
    unknown_brands: set[tuple[str, str]] = set()
    for (retailer_id, product_id), product_rows in sorted(grouped.items()):
        representative = min(product_rows, key=_rank)
        searchable = " ".join(
            value
            for value in (
                representative.title,
                representative.brand or "",
                representative.url or "",
            )
            if value
        ).casefold()
        matching_exclusion = next((term for term in exclusions if term in searchable), None)
        has_target = not targets or any(term in searchable for term in targets)
        positive_price = any(row.price is not None and row.price > 0 for row in product_rows)
        if matching_exclusion:
            admission_status = "excluded"
            admission_reason = f"Matched reviewed exclusion term: {matching_exclusion}"
        elif not has_target:
            admission_status = "review_required"
            admission_reason = "No reviewed target term was present"
        elif not positive_price:
            admission_status = "excluded"
            admission_reason = "Search returned no positive observed price"
        else:
            admission_status = "provisionally_admitted"
            admission_reason = "Matched reviewed target terms with a positive Search price"
        resolution = brand_resolver.resolve(retailer_id, representative.brand)
        if resolution.status == "unresolved" and resolution.normalized_brand:
            unknown_brands.add((retailer_id, resolution.normalized_brand))
        by_price: dict[Decimal, list[DiscoveryObservation]] = defaultdict(list)
        for row in product_rows:
            if row.price is not None and row.price > 0:
                by_price[row.price].append(row)
        contexts = tuple(
            _context(min(price_rows, key=_rank))
            for _price, price_rows in sorted(by_price.items(), key=lambda item: item[0])
        )
        prices = sorted(by_price)
        products.append(
            DiscoveryProduct(
                retailer_id=retailer_id,
                retailer_product_id=product_id,
                title=representative.title,
                brand=representative.brand,
                url=representative.url,
                image_url=representative.image_url,
                admission_status=admission_status,
                admission_reason=admission_reason,
                observation_count=len(product_rows),
                store_count=len(
                    {row.store_number for row in product_rows if row.store_number is not None}
                ),
                zipcode_count=len({row.zipcode for row in product_rows if row.zipcode is not None}),
                price_min=prices[0] if prices else None,
                price_max=prices[-1] if prices else None,
                price_contexts=contexts,
                representative_context=_context(representative),
                brand_resolution=resolution.to_record(),
                identifiers=representative.identifiers,
                source_artifact_ids=tuple(
                    sorted(
                        {
                            row.source_artifact_id
                            for row in product_rows
                            if row.source_artifact_id is not None
                        }
                    )
                ),
            )
        )
    return DiscoveryProfile(
        products=tuple(products),
        summary={
            "raw_observations": len(rows),
            "unique_products": len(products),
            "provisionally_admitted_products": sum(
                row.admission_status == "provisionally_admitted" for row in products
            ),
            "excluded_products": sum(row.admission_status == "excluded" for row in products),
            "review_required_products": sum(
                row.admission_status == "review_required" for row in products
            ),
            "unknown_brands": len(unknown_brands),
            "price_variant_contexts": sum(
                max(len(row.price_contexts) - 1, 0)
                for row in products
                if row.admission_status == "provisionally_admitted"
            ),
            "pdp_contexts": sum(
                len(row.price_contexts)
                for row in products
                if row.admission_status == "provisionally_admitted"
            ),
        },
    )


def safe_product_pack_id(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return f"fresh_{value.removeprefix('fresh_')}"[:64]
