"""Provider and adapter value objects."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    method: str
    path: str
    params: JsonObject


@dataclass(frozen=True, slots=True)
class RetailerSpec:
    retailer_id: str
    endpoint: str
    method: str
    credits_per_successful_page: int
    location_dimension: str
    required_params: tuple[str, ...]
    aliases: tuple[str, ...]
    default_sort: str | None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    initial_backoff_seconds: float = 30
    rate_limit_backoff_seconds: float = 120
    max_backoff_seconds: float = 900
    jitter: bool = True

    def delay(self, failure_class: str, attempt: int, *, retry_after: float | None = None) -> float:
        if failure_class == "rate_limit":
            base = max(self.rate_limit_backoff_seconds, retry_after or 0)
            return min(base, self.max_backoff_seconds)
        else:
            base = self.initial_backoff_seconds * (2 ** max(attempt - 1, 0))
        capped = min(base, self.max_backoff_seconds)
        if not self.jitter:
            return capped
        return min(random.uniform(0.5, 1.5) * capped, self.max_backoff_seconds)
