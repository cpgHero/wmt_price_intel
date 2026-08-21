"""Generic retail competitive analytics engine."""

from rci_analytics.assortment import AssortmentAccumulator, merge_assortment_product_context
from rci_analytics.classification import OfferClassifier
from rci_analytics.competitive_leadership import (
    CompetitiveProductLeadershipProjector,
    ProductLeadershipRelationship,
)
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
    RelationshipInputReducer,
    location_scope_key,
    product_footprint,
    resolve_one_to_one_relationships,
)
from rci_analytics.matching_v2 import (
    AttributePolicyV2,
    AttributeValue,
    DeterministicMatchEngineV2,
    IdentifierEvidence,
    ListingEvidence,
    ListingLocationEvidence,
    LocalComparisonProjectorV2,
    LocalOfferV2,
    MatchingPolicyV2,
    TieredMatchDecisionV2,
    compile_matching_policy_v2,
    reconcile_local_comparisons,
)
from rci_analytics.matching_v2_certification import (
    GoldMatchLabelV2,
    MatchingCertificationThresholdsV2,
    MatchingV2Certification,
    certify_matching_v2,
)
from rci_analytics.matching_v2_review import (
    MatchingV2ReviewSampling,
    build_matching_v2_review_queue,
    queue_cases,
)
from rci_analytics.matching_v2_shadow import (
    ListingEvidenceAccumulatorV2,
    MatchingShadowEvaluatorV2,
    MatchingShadowResultV2,
    build_listing_evidence_v2,
    shadow_result_checksum,
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
from rci_analytics.price_architecture import (
    PriceArchitectureMatrixProjector,
    PriceArchitectureRetailerInput,
)
from rci_analytics.price_monitoring import (
    PriceMonitoringFilters,
    PriceMonitoringProjector,
    classified_offer_from_record,
)
from rci_analytics.product_leadership_validation import (
    ProductLeadershipCertification,
    certify_competitive_product_leadership,
)
from rci_analytics.product_location import (
    PRODUCT_LOCATION_OBSERVATION_SCHEMA_VERSION,
    PriceLocation,
    ProductLocationObservation,
    ProductLocationPopulation,
    ProductLocationProjector,
    ProductPriceObservation,
)
from rci_analytics.product_pack import (
    CatalogProductPackLoader,
    ProductPackLoader,
    primary_exact_profile,
)
from rci_analytics.result_v2 import AnalysisResultV2Builder, ComparisonFact, evidence_set

__all__ = [
    "PRODUCT_LOCATION_OBSERVATION_SCHEMA_VERSION",
    "AnalysisResultV2Builder",
    "AssortmentAccumulator",
    "AttributePolicyV2",
    "AttributeValue",
    "CanonicalOfferNormalizer",
    "CatalogProductPackLoader",
    "ComparisonEngine",
    "ComparisonFact",
    "ComparisonInputReducer",
    "ComparisonInsightInput",
    "CompetitiveProductLeadershipProjector",
    "DeterministicInsightEngine",
    "DeterministicMatchEngineV2",
    "GoldMatchLabelV2",
    "HistoricalImportService",
    "HistoricalInputManifestLoader",
    "IdentifierEvidence",
    "InMemoryDatasetStore",
    "InMemoryHistoricalInputRepository",
    "InMemoryHistoricalObjectStore",
    "ListingEvidence",
    "ListingEvidenceAccumulatorV2",
    "ListingLocationEvidence",
    "LocalComparisonProjectorV2",
    "LocalOfferV2",
    "MatchRelationshipResolution",
    "MatchingCertificationThresholdsV2",
    "MatchingPolicyV2",
    "MatchingShadowEvaluatorV2",
    "MatchingShadowResultV2",
    "MatchingV2Certification",
    "MatchingV2ReviewSampling",
    "OfferClassifier",
    "ParquetDatasetWriter",
    "PostgresAnalysisInputRepository",
    "PriceArchitectureMatrixProjector",
    "PriceArchitectureRetailerInput",
    "PriceLocation",
    "PriceMonitoringFilters",
    "PriceMonitoringProjector",
    "ProductLeadershipCertification",
    "ProductLeadershipRelationship",
    "ProductLocationObservation",
    "ProductLocationPopulation",
    "ProductLocationProjector",
    "ProductMatchRule",
    "ProductPackLoader",
    "ProductPriceObservation",
    "RankedInsightCandidate",
    "RelationshipInputReducer",
    "S3HistoricalObjectStore",
    "TieredMatchDecisionV2",
    "benchmark_product_decisions",
    "benchmark_product_evidence",
    "benchmark_product_map_points",
    "benchmark_product_match_candidates",
    "build_listing_evidence_v2",
    "build_matching_v2_review_queue",
    "certify_competitive_product_leadership",
    "certify_matching_v2",
    "classified_offer_from_record",
    "compile_matching_policy_v2",
    "complete_attributes_from_pdp",
    "evidence_set",
    "location_scope_key",
    "merge_assortment_product_context",
    "merge_product_decision_context",
    "merge_product_evidence_summary",
    "prepare_historical_import",
    "primary_exact_profile",
    "product_context_index",
    "product_footprint",
    "queue_cases",
    "reconcile_local_comparisons",
    "resolve_one_to_one_relationships",
    "shadow_result_checksum",
]
