"""Lossless identifier and geography normalization."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

COUNTRY_ALIASES = {
    "US": "USA",
    "U.S.": "USA",
    "UNITED STATES": "USA",
    "UNITED STATES OF AMERICA": "USA",
    "PUERTO RICO": "PR",
    "AU": "AUSTRALIA",
    "MX": "MEXICO",
}

COUNTRY_ID_SUFFIXES = {
    "USA": "us",
    "PR": "pr",
    "AUSTRALIA": "au",
    "MEXICO": "mx",
    "UNKNOWN": "unknown",
}


def normalize_identifier(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def normalize_country(value: Any) -> str:
    normalized = normalize_identifier(value)
    if normalized is None:
        return "UNKNOWN"
    upper = normalized.upper()
    return COUNTRY_ALIASES.get(upper, upper)


def normalize_zipcode(value: Any, country: Any) -> str | None:
    zipcode = normalize_identifier(value)
    if zipcode is None:
        return None
    if normalize_country(country) in {"USA", "PR"} and re.fullmatch(r"\d{1,4}", zipcode):
        return zipcode.zfill(5)
    return zipcode


def normalize_alias(value: Any) -> str | None:
    normalized = normalize_identifier(value)
    return normalized.casefold() if normalized is not None else None


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold()).strip("_")
    return slug or "unknown"


def country_id_suffix(country: str) -> str:
    return COUNTRY_ID_SUFFIXES.get(country, slugify(country))


def parse_coordinate(value: Any) -> float | None:
    normalized = normalize_identifier(value)
    if normalized is None:
        return None
    return float(normalized)
