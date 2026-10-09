"""saans-api Lambda: read-only dashboard backend.

Returns a school's current STATE plus its latest reading, with provenance so the
dashboard can show the estimate disclaimer and attribution. This function holds
a DynamoDB READ policy only — no write action on saans-state, which is what makes
the "advisory/API cannot set a tier" boundary an IAM fact, not a convention.

PRIVACY: this endpoint is public. It must never return principal_email or any
contact field, even if one is present on the STATE/PROFILE item. The response is
built from an explicit allow-list of fields, so a future field added to the table
cannot leak by accident. Tests enforce this (see tests/test_api_privacy.py).
"""
import json
import os

# Fields that may NEVER appear in an API response. Checked defensively against
# the built body, not just the STATE item, so a future code change cannot leak one.
FORBIDDEN_FIELDS = frozenset({
    "principal_email", "email", "phone", "contact", "address",
    "principal", "guardian_email", "parent_email",
})

# The only top-level keys the dashboard API returns. Anything not listed here is
# dropped before the response is serialised. An allow-list, not a block-list:
# a new field added to the table stays private unless deliberately exposed.
ALLOWED_TOP_LEVEL = frozenset({
    "school_id", "tier", "band", "aqi", "advisory", "attribution",
    "limits", "state", "latest_reading", "error",
})

ALLOWED_READING_KEYS = frozenset({
    "timestamp_utc", "pm2_5", "pm10", "aqi", "dominant_pollutant",
    "source", "modeled", "stale", "breakpoint_version",
})


def _table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])


def _cors_origin():
    """The dashboard origin this API allows. From env (set by the template from
    the DashboardOrigin parameter). Never '*'."""
    return os.environ.get("DASHBOARD_ORIGIN", "https://saans.langersword.in")


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": _cors_origin(),
            "Vary": "Origin",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }


def _strip_forbidden(obj):
    """Recursively drop any forbidden field. Defence in depth behind the
    allow-list: even if a forbidden key slipped into a nested object, it is
    removed here before serialisation."""
    if isinstance(obj, dict):
        return {k: _strip_forbidden(v) for k, v in obj.items()
                if k not in FORBIDDEN_FIELDS}
    if isinstance(obj, list):
        return [_strip_forbidden(x) for x in obj]
    return obj


def handler(event, context=None):
    from core import rules
    table = _table()

    school_id = (event.get("pathParameters") or {}).get("school_id")
    if not school_id:
        return _resp(400, _strip_forbidden({"error": "school_id is required"}))

    state = table.get_item(Key={"PK": f"SCHOOL#{school_id}", "SK": "STATE"}).get("Item")
    if not state:
        return _resp(404, _strip_forbidden({"error": f"no state for {school_id}"}))

    # Latest reading, for provenance and the raw numbers behind the tier.
    r = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={":pk": f"SCHOOL#{school_id}", ":sk": "READING#"},
        ScanIndexForward=False, Limit=1,
    ).get("Items", [])
    reading = r[0] if r else None

    tier = int(state["tier"])
    band = state["band"]
    # Build the body from the allow-list only.
    body = {
        "school_id": school_id,
        "tier": tier,
        "band": band,
        "aqi": state.get("aqi"),
        "advisory": rules.advisory_text(band),     # includes the estimate disclaimer
        "attribution": "Open-Meteo.com from CAMS, CC-BY 4.0. Modeled, not a station measurement.",
        "limits": rules.STATED_LIMITS,
        "state": {
            "prev_tier": state.get("prev_tier"),
            "pending_tier": state.get("pending_tier"),
            "pending_count": state.get("pending_count", 0),
            "stale_input": state.get("stale_input", False),
            "breakpoint_version": state.get("breakpoint_version"),
        },
    }
    if reading:
        body["latest_reading"] = {
            k: reading.get(k) for k in ALLOWED_READING_KEYS
        }

    # Final gate: allow-list the top level, then strip any forbidden field that
    # somehow survived. Both layers must pass before the body leaves the function.
    body = {k: v for k, v in body.items() if k in ALLOWED_TOP_LEVEL}
    body = _strip_forbidden(body)
    return _resp(200, body)
