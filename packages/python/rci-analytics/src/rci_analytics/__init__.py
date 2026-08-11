"""Generic retail competitive analytics engine."""

from rci_analytics.assortment import AssortmentAccumulator, merge_assortment_product_context
from rci_analytics.classification import OfferClassifier
from rci_analytics.historical import (
    HistoricalImportService,
    HistoricalInputManifestLoader,
    InMemoryHistoricalInputRepository,
    InMemoryHistoricalObjectStore,
    prepare_historical_import,
)
from rci_analytics.historical_repository import PostgresAnalysisInputRepository
from rci_analytics.historical_storage import S3HistoricalObjectStore
from rci_analytics.insights import (
    ComparisonInsightInput,
    DeterministicInsightEngine,
    RankedInsightCandidate,
)
from rci_analytics.matching import (
    ComparisonEngine,
    ComparisonInputReducer,
    MatchRelationshipResolution,
    resolve_one_to_one_relationships,
)
from rci_analytics.models import ProductMatchRule
from rci_analytics.normalization import CanonicalOfferNormalizer
from rci_analytics.parquet import InMemoryDatasetStore, ParquetDatasetWriter
from rci_analytics.pdp_attributes import complete_attributes_from_pdp, product_context_index
from rci_analytics.presentation import (
    benchmark_product_decisions,
    benchmark_product_evidence,
    benchmark_product_map_points,
    benchmark_product_match_candidates,
    merge_product_decision_context,
    merge_product_evidence_summary,
)
from rci_analytics.product_pack import (
    CatalogProductPackLoader,
    ProductPackLoader,
    primary_exact_profile,
)
from rci_analytics.result_v2 import AnalysisResultV2Builder, ComparisonFact, evidence_set

__all__ = [
    "AnalysisResultV2Builder",
    "AssortmentAccumulator",
    "CanonicalOfferNormalizer",
    "CatalogProductPackLoader",
    "ComparisonEngine",
    "ComparisonFact",
    "ComparisonInputReducer",
    "ComparisonInsightInput",
    "DeterministicInsightEngine",
    "HistoricalImportService",
    "HistoricalInputManifestLoader",
    "InMemoryDatasetStore",
    "InMemoryHistoricalInputRepository",
    "InMemoryHistoricalObjectStore",
    "MatchRelationshipResolution",
    "OfferClassifier",
    "ParquetDatasetWriter",
    "PostgresAnalysisInputRepository",
    "ProductMatchRule",
    "ProductPackLoader",
    "RankedInsightCandidate",
    "S3HistoricalObjectStore",
    "benchmark_product_decisions",
    "benchmark_product_evidence",
    "benchmark_product_map_points",
    "benchmark_product_match_candidates",
    "complete_attributes_from_pdp",
    "evidence_set",
    "merge_assortment_product_context",
    "merge_product_decision_context",
    "merge_product_evidence_summary",
    "prepare_historical_import",
    "primary_exact_profile",
    "product_context_index",
    "resolve_one_to_one_relationships",
]
