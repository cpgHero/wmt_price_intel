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
from rci_analytics.matching import ComparisonEngine
from rci_analytics.normalization import CanonicalOfferNormalizer
from rci_analytics.parquet import InMemoryDatasetStore, ParquetDatasetWriter
from rci_analytics.product_pack import ProductPackLoader

__all__ = [
    "CanonicalOfferNormalizer",
    "ComparisonEngine",
    "HistoricalImportService",
    "HistoricalInputManifestLoader",
    "InMemoryDatasetStore",
    "InMemoryHistoricalInputRepository",
    "InMemoryHistoricalObjectStore",
    "OfferClassifier",
    "ParquetDatasetWriter",
    "PostgresAnalysisInputRepository",
    "ProductPackLoader",
    "S3HistoricalObjectStore",
    "prepare_historical_import",
]
