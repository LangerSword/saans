"""ddb module tests — pinning the two bugs the live smoke test found.

1. DynamoDB put_item rejects Python floats ("Float types are not supported.
   Use Decimal types instead.").
2. Reads return Decimal everywhere (integers included) and json.dumps refuses
   Decimal — so the API must convert back before serialising.
"""
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import ddb  # noqa: E402


def test_float_to_decimal_exact():
    """87.1 must become Decimal('87.1'), not the binary-float expansion."""
    assert ddb.to_ddb(87.1) == Decimal("87.1")
    assert str(ddb.to_ddb(87.1)) == "87.1"


def test_int_left_alone():
    out = ddb.to_ddb(3)
    assert out == 3
    assert isinstance(out, int)


def test_none_bool_str_untouched():
    assert ddb.to_ddb(None) is None
    assert ddb.to_ddb(True) is True
    assert ddb.to_ddb("poor") == "poor"


def test_nested_structures():
    item = {"aqi": 87.1, "list": [1.5, {"pm2_5": 36.4}], "n": None}
    out = ddb.to_ddb(item)
    assert out["aqi"] == Decimal("87.1")
    assert out["list"][0] == Decimal("1.5")
    assert out["list"][1]["pm2_5"] == Decimal("36.4")
    assert out["n"] is None


def test_from_ddb_integral_to_int():
    out = ddb.from_ddb(Decimal("170"))
    assert out == 170
    assert isinstance(out, int)


def test_from_ddb_fractional_to_float():
    out = ddb.from_ddb(Decimal("87.1"))
    assert out == 87.1
    assert isinstance(out, float)


def test_round_trip_is_json_serialisable():
    """The full loop the API does: stored item -> response body -> json.dumps."""
    payload = {"aqi": 87.1, "tier": 1, "reading": {"pm2_5": 36.4, "pm10": None}}
    back = ddb.from_ddb(ddb.to_ddb(payload))
    assert json.loads(json.dumps(back)) == payload
