from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rci_contracts import validate_instance
from rci_products.adapters import MetricsCartProductDetailAdapter
from rci_products.catalog import ProductDetailCatalog
from rci_products.documents import normalization_document, snapshot_document
from rci_products.models import (
    ProductDetailFetchResult,
    ProductDetailJob,
    ProductDetailNormalizationCandidate,
    ProductDetailRawArtifact,
    ProductDetailRequestContext,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = REPOSITORY_ROOT / "fixtures" / "api_samples"


@pytest.mark.parametrize(
    ("retailer_id", "fixture_name", "context", "expected_category", "expected_id"),
    [
        (
            "walmart_us",
            "metricscart_pdp_walmart_200.json",
            ProductDetailRequestContext(
                product_id="677669806",
                zipcode="90020",
                store="2464",
                fulfillment_type="pickup",
            ),
            "Food > Snacks, Cookies & Chips > Chips > Lay's Potato Chips",
            "677669806",
        ),
        (
            "aldi_us",
            "metricscart_pdp_aldi_200.json",
            ProductDetailRequestContext(
                product_id="0000000000008696",
                zipcode="90001",
                store="479-149",
                fulfillment_type="pickup",
            ),
            "Fresh Meat & Seafood > Fresh Seafood",
            "0000000000008696",
        ),
        (
            "amazon_us_same_day",
            "metricscart_pdp_amazon_200.json",
            ProductDetailRequestContext(product_id="B0DN1ZTN12", zipcode="90001"),
            "Electronics > Computers & Accessories > Computers & Tablets",
            "B0DN1ZTN12",
        ),
    ],
)
def test_pdp_fixtures_build_requests_and_normalize_to_valid_snapshots(
    retailer_id: str,
    fixture_name: str,
    context: ProductDetailRequestContext,
    expected_category: str,
    expected_id: str,
) -> None:
    catalog = ProductDetailCatalog.from_path(REPOSITORY_ROOT)
    endpoint = catalog.get(retailer_id)
    adapter = MetricsCartProductDetailAdapter(endpoint)
    request = adapter.build_request(context)
    payload = json.loads((FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8"))
    normalized = adapter.normalize(payload, context)
    job = ProductDetailJob(
        id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        canonical_product_db_id="00000000-0000-0000-0000-000000000003",
        canonical_product_id=f"{retailer_id}:{expected_id}",
        retailer_id=retailer_id,
        endpoint=endpoint,
        context=context,
        request_checksum=context.checksum(endpoint),
        credits_per_call=endpoint.credits_per_successful_page,
        status="running",
        attempt_count=1,
        max_attempts=3,
    )
    result = ProductDetailFetchResult(
        observed_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
        http_status=200,
        billable=True,
        credits=endpoint.credits_per_successful_page,
        raw_artifact=ProductDetailRawArtifact(
            artifact_id="raw-fixture",
            storage_uri="s3://fixture/pdp.json.gz",
            checksum="a" * 64,
            byte_size=1,
            metadata={},
        ),
        normalized=normalized,
    )
    document = snapshot_document(job, result, snapshot_id="snapshot-fixture")

    assert request.params["product_id"] == expected_id
    if retailer_id == "amazon_us_same_day":
        assert request.path == "/mc/amazon/pdp/zipcode/"
    if retailer_id == "aldi_us":
        assert request.path == "/mc/new_aldi/pdp/zipcode/"
    if retailer_id == "walmart_us":
        assert request.path == "/mc/walmart/product/zipcode/"
    assert normalized.retailer_product_id == expected_id
    assert normalized.category_path == expected_category
    validate_instance(
        REPOSITORY_ROOT,
        "product-detail-snapshot.schema.json",
        document,
        label=fixture_name,
    )


def test_request_builder_preserves_leading_zero_ids_and_rejects_missing_context() -> None:
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("aldi_us")
    adapter = MetricsCartProductDetailAdapter(endpoint)
    request = adapter.build_request(
        ProductDetailRequestContext(
            product_id="0000000000008696",
            zipcode="00501",
            store="479-149",
            fulfillment_type="pickup",
        )
    )

    assert request.params["product_id"] == "0000000000008696"
    assert request.params["zipcode"] == "00501"
    with pytest.raises(ValueError, match="missing required"):
        adapter.build_request(
            ProductDetailRequestContext(product_id="0000000000008696", zipcode="00501")
        )


def test_pdp_seller_is_preserved_as_identity_evidence() -> None:
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us")
    context = ProductDetailRequestContext(
        product_id="677669806",
        zipcode="90020",
        store="2464",
        fulfillment_type="pickup",
    )
    normalized = MetricsCartProductDetailAdapter(endpoint).normalize(
        {
            "name": "Lay's Classic Potato Chips",
            "retailer_product_id": "677669806",
            "seller": "Walmart.com",
        },
        context,
    )

    assert normalized.seller == "Walmart.com"
    assert normalized.identity_document()["seller"] == "Walmart.com"
    assert normalized.contract_document()["seller"] == "Walmart.com"


def test_full_pdp_payload_is_governed_into_useful_evidence_groups() -> None:
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us")
    context = ProductDetailRequestContext(
        product_id="677669806",
        zipcode="90020",
        store="2464",
        fulfillment_type="pickup",
    )
    payload = json.loads(
        (FIXTURE_ROOT / "metricscart_pdp_walmart_200.json").read_text(encoding="utf-8")
    )
    normalized = MetricsCartProductDetailAdapter(endpoint).normalize(payload, context)
    document = normalized.contract_document()

    assert document["normalizer_version"] == "2.0.0"
    assert normalized.seller == "Walmart.com"
    assert normalized.identity_document()["item_condition"] == "New"
    assert document["commerce"]["price_regular"] == 4.77
    assert document["commerce"]["offers"] == []
    assert document["fulfillment"]["fulfilled_by_retailer"] is True
    assert document["fulfillment"]["returnable_in"] == 90
    assert document["reviews"]["rating"] == 4.7
    assert document["reviews"]["reviews_count"] == 2358
    assert document["demand"]["weekly_sales_volume"] == 10000
    assert document["content"]["has_enhanced_content"] is True
    assert document["relationships"]["variants"] == []
    assert document["source_context"] == {
        "zipcode": "90020",
        "retailer": "walmart.com",
        "source": "pdp",
    }
    assert document["unmapped_source_fields"] == []
    assert set(document["source_field_inventory"]) == set(payload)
    revision = normalization_document(
        ProductDetailNormalizationCandidate(
            id="00000000-0000-0000-0000-000000000011",
            snapshot_id="00000000-0000-0000-0000-000000000012",
            normalizer_version="2.0.0",
            canonical_product_db_id="00000000-0000-0000-0000-000000000013",
            canonical_product_id="walmart_us:677669806",
            retailer_id="walmart_us",
            raw_storage_uri="s3://fixture/pdp.json.gz",
            raw_checksum="a" * 64,
            endpoint=endpoint,
            context=context,
            attempt_count=1,
        ),
        normalized,
    )
    validate_instance(
        REPOSITORY_ROOT,
        "product-detail-normalization.schema.json",
        revision,
        label="full PDP normalization",
    )


def test_unrecognized_pdp_fields_are_visible_for_schema_drift_review() -> None:
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us")
    context = ProductDetailRequestContext(product_id="677669806")
    normalized = MetricsCartProductDetailAdapter(endpoint).normalize(
        {
            "name": "Test product",
            "retailer_product_id": "677669806",
            "future_provider_field": {"useful": True},
        },
        context,
    )

    assert normalized.unmapped_source_fields == ("future_provider_field",)


def test_aldi_request_matches_verified_zipcode_contract() -> None:
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("aldi_us")
    adapter = MetricsCartProductDetailAdapter(endpoint)
    context = ProductDetailRequestContext(
        product_id="17499083",
        zipcode="71111",
        store="475-107",
        fulfillment_type="pickup",
    )
    request = adapter.build_request(context)
    normalized = adapter.normalize(
        {
            "name": "73% Lean 27% Fat Ground Beef",
            "retailer_product_id": "17499083",
            "retailer_store_id": "512548",
        },
        context,
    )

    assert request.method == "GET"
    assert request.path == "/mc/new_aldi/pdp/zipcode/"
    assert request.params == {
        "product_id": "17499083",
        "zipcode": "71111",
        "store": "475-107",
        "fulfillment_type": "pickup",
    }
    assert context.store == "475-107"
    assert normalized.extras["retailer_store_id"] == "512548"


def test_walmart_request_matches_verified_zipcode_contract() -> None:
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get("walmart_us")
    request = MetricsCartProductDetailAdapter(endpoint).build_request(
        ProductDetailRequestContext(
            product_id="15136790",
            zipcode="03038",
            store="1753",
            fulfillment_type="pickup",
        )
    )

    assert request.method == "GET"
    assert request.path == "/mc/walmart/product/zipcode/"
    assert request.params == {
        "product_id": "15136790",
        "zipcode": "03038",
        "store": "1753",
        "fulfillment_type": "pickup",
    }


@pytest.mark.parametrize(
    ("retailer_id", "product_id", "zipcode", "store", "expected_path"),
    [
        ("heb_us", "5819025", "77084", "497", "/mc/heb/pdp/zipcode/"),
        (
            "safeway_us",
            "105300071",
            "94611",
            "3132",
            "/mc/safeway/pdp/zipcode/",
        ),
    ],
)
def test_regional_retailer_requests_preserve_verified_trailing_slash(
    retailer_id: str,
    product_id: str,
    zipcode: str,
    store: str,
    expected_path: str,
) -> None:
    endpoint = ProductDetailCatalog.from_path(REPOSITORY_ROOT).get(retailer_id)
    request = MetricsCartProductDetailAdapter(endpoint).build_request(
        ProductDetailRequestContext(
            product_id=product_id,
            zipcode=zipcode,
            store=store,
        )
    )

    assert request.method == "GET"
    assert request.path == expected_path
    assert request.params == {
        "product_id": product_id,
        "zipcode": zipcode,
        "store": store,
    }
