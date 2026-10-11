"""Float<->Decimal conversion for DynamoDB.

DynamoDB (via the boto3 resource interface) rejects Python floats outright
("Float types are not supported. Use Decimal types instead."). Items must carry
Decimal. Reads come back as Decimal everywhere, including integers, which
`json.dumps` then refuses — so the API converts back before serialising.

One module for both directions so they cannot drift apart.
Found by the first live smoke test, 2026-10-12.
"""
from decimal import Decimal


def to_ddb(obj):
    """Recursively convert float -> Decimal.

    Uses str() so 87.1 becomes Decimal('87.1') — the decimal we mean — not the
    binary-float expansion Decimal(87.1) would produce.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: to_ddb(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_ddb(v) for v in obj]
    return obj


def from_ddb(obj):
    """Recursively convert Decimal -> int (when integral) or float, for JSON."""
    if isinstance(obj, Decimal):
        if obj == obj.to_integral_value():
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: from_ddb(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [from_ddb(v) for v in obj]
    return obj
