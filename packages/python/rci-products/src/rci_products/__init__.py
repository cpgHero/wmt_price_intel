"""Canonical product identity and Product Details enrichment."""

from rci_products.adapters import MetricsCartProductDetailAdapter
from rci_products.catalog import ProductDetailCatalog
from rci_products.client import (
    MetricsCartProductDetailClient,
    PostgresProductDetailLimiterRegistry,
    ProductDetailTransportFailure,
    StaticProductDetailLimiterRegistry,
)
from rci_products.documents import (
    attach_product_identity,
    canonical_product_document,
    snapshot_document,
    source_context,
)
from rci_products.memory import InMemoryProductDetailRepository
from rci_products.models import (
    PRODUCT_DETAIL_NORMALIZER_VERSION,
    CanonicalProductRecord,
    EnqueueProductDetailResult,
    NormalizedProductDetail,
    ProductDetailEndpoint,
    ProductDetailFetchResult,
    ProductDetailJob,
    ProductDetailNormalizationCandidate,
    ProductDetailNormalizationRecord,
    ProductDetailRawArtifact,
    ProductDetailRequestContext,
    ProductDetailRun,
    ProductDetailSnapshotRecord,
)
from rci_products.planning import ProductDetailCandidate, plan_product_detail_candidates
from rci_products.postgres import PostgresProductDetailRepository
from rci_products.renormalization import ProductDetailRenormalizationWorker
from rci_products.repository import ProductDetailBudgetExceeded, ProductDetailRepository
from rci_products.service import ProductDetailWorker
from rci_products.storage import (
    InMemoryProductDetailRawObjectStore,
    S3ProductDetailRawObjectStore,
)

__all__ = [
    "PRODUCT_DETAIL_NORMALIZER_VERSION",
    "CanonicalProductRecord",
    "EnqueueProductDetailResult",
    "InMemoryProductDetailRawObjectStore",
    "InMemoryProductDetailRepository",
    "MetricsCartProductDetailAdapter",
    "MetricsCartProductDetailClient",
    "NormalizedProductDetail",
    "PostgresProductDetailLimiterRegistry",
    "PostgresProductDetailRepository",
    "ProductDetailBudgetExceeded",
    "ProductDetailCandidate",
    "ProductDetailCatalog",
    "ProductDetailEndpoint",
    "ProductDetailFetchResult",
    "ProductDetailJob",
    "ProductDetailNormalizationCandidate",
    "ProductDetailNormalizationRecord",
    "ProductDetailRawArtifact",
    "ProductDetailRenormalizationWorker",
    "ProductDetailRepository",
    "ProductDetailRequestContext",
    "ProductDetailRun",
    "ProductDetailSnapshotRecord",
    "ProductDetailTransportFailure",
    "ProductDetailWorker",
    "S3ProductDetailRawObjectStore",
    "StaticProductDetailLimiterRegistry",
    "attach_product_identity",
    "canonical_product_document",
    "plan_product_detail_candidates",
    "snapshot_document",
    "source_context",
]
