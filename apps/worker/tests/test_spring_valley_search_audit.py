import importlib.util
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest


def _audit_module() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts" / "audit_spring_valley_search.py"
    spec = importlib.util.spec_from_file_location("spring_valley_search_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the Spring Valley Search audit module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_credit_ceiling = _audit_module()._credit_ceiling


def test_credit_ceiling_converts_approved_usd_without_rounding_up() -> None:
    assert _credit_ceiling(Decimal("15.00")) == 7_500
    assert _credit_ceiling(Decimal("10.671")) == 5_335


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-1"), Decimal("NaN")])
def test_credit_ceiling_rejects_invalid_approval(value: Decimal) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        _credit_ceiling(value)
