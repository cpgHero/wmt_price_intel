from __future__ import annotations

import pytest

from rci_worker.pdp_recover_raw import classify_raw_payload


def test_classifies_named_pdp_payload_as_billable_success() -> None:
    result = classify_raw_payload({"name": "Kroger Grade A Large White Eggs"})

    assert result.http_status == 200
    assert result.billable is True
    assert result.should_retry is False


def test_classifies_explicit_rate_limit_payload_as_retryable_nonbillable() -> None:
    result = classify_raw_payload({"message": "API rate limit exceeded"})

    assert result.http_status == 429
    assert result.billable is False
    assert result.failure_class == "rate_limit"
    assert result.should_retry is True


def test_rejects_ambiguous_raw_payload() -> None:
    with pytest.raises(ValueError, match="unambiguous"):
        classify_raw_payload({"error": "unknown provider response"})
