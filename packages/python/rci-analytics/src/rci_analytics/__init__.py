"""Generic retail competitive analytics engine."""

from rci_analytics.classification import OfferClassifier
from rci_analytics.matching import ComparisonEngine
from rci_analytics.normalization import CanonicalOfferNormalizer
from rci_analytics.parquet import InMemoryDatasetStore, ParquetDatasetWriter
from rci_analytics.product_pack import ProductPackLoader

__all__ = [
    "CanonicalOfferNormalizer",
    "ComparisonEngine",
    "InMemoryDatasetStore",
    "OfferClassifier",
    "ParquetDatasetWriter",
    "ProductPackLoader",
]
