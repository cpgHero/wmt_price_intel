from __future__ import annotations

import pytest

from rci_worker.product_enrichment import _selected_product_pack_version


def test_product_enrichment_uses_the_source_analysis_pack_by_default() -> None:
    assert _selected_product_pack_version("1.0.0", None) == "1.0.0"


def test_product_enrichment_accepts_an_exact_pack_override() -> None:
    assert _selected_product_pack_version("1.0.0", " 1.2.1 ") == "1.2.1"


def test_product_enrichment_rejects_an_empty_pack_override() -> None:
    with pytest.raises(ValueError, match="Product Pack version cannot be empty"):
        _selected_product_pack_version("1.0.0", "   ")
