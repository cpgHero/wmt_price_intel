"""Category-neutral package quantity semantics used by matching and metrics."""

from __future__ import annotations

import re
from decimal import Decimal

_WEIGHT = r"\d+(?:\.\d+)?\s*(?:lb|lbs|pounds?|oz|ounces?|kg|g)\b"
_LABELED_UNIT_COUNT = re.compile(
    rf"(?:{_WEIGHT}\s*[,;/\-]?\s*(\d+)\s*(?:count|ct|pack(?:age)?s?)\b|"
    rf"(\d+)\s*[x\u00d7]\s*{_WEIGHT}|"
    rf"pack\s+of\s+(\d+)\s*[,;/\-]?\s*{_WEIGHT})",
    flags=re.IGNORECASE,
)


def labeled_unit_pack_count(title: str) -> int:
    """Return an explicit multipack count when a title also states unit weight."""

    match = _LABELED_UNIT_COUNT.search(title)
    if match is None:
        return 1
    return int(next(value for value in match.groups() if value is not None))


def labeled_unit_packs_are_compatible(left: str, right: str) -> bool:
    """Protect package-price comparisons from unit-versus-multipack distortion."""

    return labeled_unit_pack_count(left) == labeled_unit_pack_count(right)


def effective_package_measure(title: str, measure: Decimal | None) -> Decimal | None:
    """Convert an explicit per-unit measure into the package-total measure.

    Product titles often state a unit measure followed by the number of units,
    for example ``1 lb, 3 Count``. Product Pack measurement extraction correctly
    captures the labeled unit as one pound; normalized-price formulas need the
    package-total measure of three pounds.
    """

    if measure is None:
        return None
    return measure * labeled_unit_pack_count(title)
