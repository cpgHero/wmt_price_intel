from __future__ import annotations

from decimal import Decimal

from rci_products import plan_product_detail_candidates


def _observation(
    offer_id: str,
    product_id: str,
    zipcode: str,
    store: str,
    price: float,
) -> dict[str, object]:
    return {
        "offer_id": offer_id,
        "retailer_id": "walmart_us",
        "retailer_product_id": product_id,
        "zipcode": zipcode,
        "store_number": store,
        "fulfillment_type": "pickup",
        "product_url": f"https://www.walmart.com/ip/{product_id}",
        "price": price,
    }


def test_pdp_plan_excludes_search_noise_and_deduplicates_locations() -> None:
    observations = [
        _observation("analysis-a", "100", "72712", "1", 4.98),
        _observation("analysis-b", "100", "90210", "2", 4.98),
        _observation("noise", "999", "10001", "3", 9.98),
    ]

    candidates = plan_product_detail_candidates(
        observations,
        analysis_offer_ids={"analysis-a", "analysis-b"},
    )

    assert len(candidates) == 1
    assert candidates[0].retailer_product_id == "100"
    assert candidates[0].context.zipcode == "72712"
    assert candidates[0].reason == "product_reference"


def test_pdp_plan_keeps_one_location_per_distinct_product_price() -> None:
    observations = [
        _observation("price-a-1", "100", "72712", "1", 4.98),
        _observation("price-a-2", "100", "72713", "2", 4.98),
        _observation("price-b-1", "100", "90210", "3", 5.48),
        _observation("price-b-2", "100", "90211", "4", 5.48),
    ]

    candidates = plan_product_detail_candidates(
        observations,
        analysis_offer_ids={str(row["offer_id"]) for row in observations},
    )

    assert [candidate.observed_price for candidate in candidates] == [
        Decimal("4.98"),
        Decimal("5.48"),
    ]
    assert [candidate.context.zipcode for candidate in candidates] == ["72712", "90210"]
    assert {candidate.reason for candidate in candidates} == {"location_price_variant"}


def test_missing_price_does_not_create_a_false_location_variant() -> None:
    observations = [
        _observation("known", "100", "72712", "1", 4.98),
        {
            **_observation("missing", "100", "90210", "2", 4.98),
            "price": None,
        },
    ]

    candidates = plan_product_detail_candidates(
        observations,
        analysis_offer_ids={"known", "missing"},
    )

    assert len(candidates) == 1
    assert candidates[0].observed_price == Decimal("4.98")
    assert candidates[0].context.zipcode == "72712"
    assert candidates[0].reason == "product_reference"


def test_pdp_plan_requires_a_positive_search_price() -> None:
    observations = [
        _observation("zero", "100", "72712", "1", 0),
        {**_observation("missing", "101", "90210", "2", 4.98), "price": None},
    ]

    candidates = plan_product_detail_candidates(
        observations,
        analysis_offer_ids={"zero", "missing"},
    )

    assert candidates == []
