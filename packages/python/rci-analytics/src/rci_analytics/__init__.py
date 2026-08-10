"""Generic retail competitive analytics engine."""

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
from rci_analytics.matching import ComparisonEngine, ComparisonInputReducer
from rci_analytics.normalization import CanonicalOfferNormalizer
from rci_analytics.parquet import InMemoryDatasetStore, ParquetDatasetWriter
from rci_analytics.pdp_attributes import complete_attributes_from_pdp, product_context_index
from rci_analytics.presentation import (
    benchmark_product_decisions,
    benchmark_product_evidence,
    benchmark_product_map_points,
    merge_product_decision_context,
    merge_product_evidence_summary,
)
from rci_analytics.product_pack import ProductPackLoader, primary_exact_profile
from rci_analytics.result_v2 import AnalysisResultV2Builder, ComparisonFact, evidence_set

__all__ = [
    "AnalysisResultV2Builder",
    "CanonicalOfferNormalizer",
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
    "OfferClassifier",
    "ParquetDatasetWriter",
    "PostgresAnalysisInputRepository",
    "ProductPackLoader",
    "RankedInsightCandidate",
    "S3HistoricalObjectStore",
    "benchmark_product_decisions",
    "benchmark_product_evidence",
    "benchmark_product_map_points",
    "complete_attributes_from_pdp",
    "evidence_set",
    "merge_product_decision_context",
    "merge_product_evidence_summary",
    "prepare_historical_import",
    "primary_exact_profile",
    "product_context_index",
]
