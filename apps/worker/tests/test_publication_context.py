from rci_worker.publication_context import (
    _raw_quality_observation,
    _select_quality_observations,
)


def test_raw_quality_observation_preserves_search_identity() -> None:
    row = {
        "Product Name": "Fresh Ground Beef",
        "Retailer Product Id": "abc-123",
        "Price": "",
        "Zipcode": "00501",
        "Retailer Store Id": "0042",
        "Url": "https://example.test/product/abc-123",
    }

    observation = _raw_quality_observation(
        row,
        retailer_id="walmart_us",
        issue="Normalization rejected",
        reason="test rejection",
    )

    assert observation["product"] == "Fresh Ground Beef"
    assert observation["product_id"] == "abc-123"
    assert observation["zipcode"] == "00501"
    assert observation["store"] == "0042"
    assert observation["source_url"] == "https://example.test/product/abc-123"


def test_quality_sample_is_balanced_stable_and_deduplicated() -> None:
    rows = [
        {
            "issue": issue,
            "retailer": "walmart_us",
            "product": f"Product {index}",
            "product_id": f"id-{issue}-{index}",
            "zipcode": "00501",
            "store": str(index),
            "reason": issue,
        }
        for issue in (
            "Missing or zero search price",
            "Attribute review",
            "Normalization rejected",
        )
        for index in range(3)
    ]
    rows.append(dict(rows[0]))

    selected = _select_quality_observations(rows, max_rows=6)

    assert len(selected) == 6
    assert {row["issue"] for row in selected} == {
        "Missing or zero search price",
        "Attribute review",
        "Normalization rejected",
    }
    assert len({str(row["product_id"]) for row in selected}) == 6
