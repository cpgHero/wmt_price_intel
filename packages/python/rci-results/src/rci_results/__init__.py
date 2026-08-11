"""Canonical AnalysisResult persistence and delivery."""

from rci_results.blueprints import ReportBlueprintLoader, ReportProjector
from rci_results.brand_review import (
    BrandDecisionCommand,
    BrandReanalysisRecord,
    BrandReviewService,
    BrandRevisionConflictError,
    InMemoryBrandReviewRepository,
    PostgresBrandReviewRepository,
)
from rci_results.contracts import AnalysisResultValidator, ReportViewValidator
from rci_results.match_review import (
    InMemoryMatchReviewRepository,
    MatchDecisionCommand,
    MatchOneToOneConflictError,
    MatchReanalysisRecord,
    MatchReviewService,
    MatchRevisionConflictError,
    PostgresMatchReviewRepository,
)
from rci_results.memory import InMemoryResultsRepository
from rci_results.models import AnalysisPublicationRecord
from rci_results.renderers import ArtifactRenderer
from rci_results.repository import PostgresResultsRepository
from rci_results.service import AnalysisResultService
from rci_results.storage import InMemoryReportObjectStore, S3ReportObjectStore

__all__ = [
    "AnalysisPublicationRecord",
    "AnalysisResultService",
    "AnalysisResultValidator",
    "ArtifactRenderer",
    "BrandDecisionCommand",
    "BrandReanalysisRecord",
    "BrandReviewService",
    "BrandRevisionConflictError",
    "InMemoryBrandReviewRepository",
    "InMemoryMatchReviewRepository",
    "InMemoryReportObjectStore",
    "InMemoryResultsRepository",
    "MatchDecisionCommand",
    "MatchOneToOneConflictError",
    "MatchReanalysisRecord",
    "MatchReviewService",
    "MatchRevisionConflictError",
    "PostgresBrandReviewRepository",
    "PostgresMatchReviewRepository",
    "PostgresResultsRepository",
    "ReportBlueprintLoader",
    "ReportProjector",
    "ReportViewValidator",
    "S3ReportObjectStore",
]
