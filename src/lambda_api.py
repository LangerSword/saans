"""saans-api Lambda: read-only dashboard backend.

Returns a school's current STATE (saans-state) plus its generated ADVISORY
(saans-content) and latest reading, with provenance so the dashboard can show
the estimate disclaimer, attribution, and which writer produced the advisory
(bedrock or template). This function holds READ-ONLY policies on both tables —
no write action anywhere, which makes "the API cannot set a tier" an IAM fact,
not a convention.

PRIVACY: this endpoint is public. It must never return principal_email or any
contact field, even if one is present on the items. The response is built from
an explicit allow-list of fields, so a future field added to a table cannot
leak by accident. Tests enforce this (see tests/test_api_privacy.py).

CORS: allowed origins are an explicit allowlist (DASHBOARD_ORIGINS env,
comma-separated; falls back to DASHBOARD_ORIGIN). The request's Origin is
echoed only when it is in the list — never "*".
"""
import json
import os

# Fields that may NEVER appear in an API response. Checked defensively against
# the built body, not just the source items, so a future code change cannot leak one.
FORBIDDEN_FIELDS = frozenset({
    "principal_email", "email", "phone", "contact", "address",
    "principal", "guardian_email", "parent_email",
})

# The only top-level keys the dashboard API returns. Anything not listed here is
# dropped before the response is serialised. An allow-list, not a block-list:
# a new field added to a table stays private unless deliberately exposed.
ALLOWED_TOP_LEVEL = frozenset({
    "school_id", "school_name", "tier", "band", "aqi",
    "advisory", "advisory_all", "advisory_source", "advisory_generated_at",
    "attribution", "limits", "state", "latest_reading", "error",
})

ALLOWED_READING_KEYS = frozenset({
    "timestamp_utc", "pm2_5", "pm10", "aqi", "dominant_pollutant",
    "source", "modeled", "stale", "breakpoint_version",
})


def _table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])


def _content_table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["CONTENT_TABLE"])


def _allowed_origins():
    raw = (os.environ.get("DASHBOARD_ORIGINS")
           or os.environ.get("DASHBOARD_ORIGIN")
           or "https://saans.langersword.in")
    return [o.strip() for o in raw.split(",") if o.strip()]


def _cors_origin(event=None):
    """Echo the request Origin only when it is in the allowlist; else primary.

    Never '*' — the allowlist is the whole point.
    """
    allowed = _allowed_origins()
    headers = (event or {}).get("headers") or {}
    origin = headers.get("origin") or headers.get("Origin")
    if origin in allowed:
        return origin
    return allowed[0]


def _resp(status, body, origin):
    # from_ddb: DynamoDB returns every number as Decimal (integers included) and
    # json.dumps refuses Decimal. Convert back to int/float before serialising.
    from core import ddb
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
        },
        "body": json.dumps(ddb.from_ddb(body), ensure_ascii=False),
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
    from core import rules, seed

    table = _table()
    origin = _cors_origin(event)

    school_id = (event.get("pathParameters") or {}).get("school_id")
    if not school_id:
        return _resp(400, _strip_forbidden({"error": "school_id is required"}), origin)

    state = table.get_item(Key={"PK": f"SCHOOL#{school_id}", "SK": "STATE"}).get("Item")
    if not state:
        return _resp(404, _strip_forbidden({"error": f"no state for {school_id}"}), origin)

    # Latest reading, for provenance and the raw numbers behind the tier.
    r = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={":pk": f"SCHOOL#{school_id}", ":sk": "READING#"},
        ScanIndexForward=False, Limit=1,
    ).get("Items", [])
    reading = r[0] if r else None

    # The generated advisory (EN/HI/TE) lives in saans-content. A missing item
    # is fine — fall back to the computed EN text so the dashboard never blanks.
    adv = None
    try:
        adv = _content_table().get_item(
            Key={"PK": f"SCHOOL#{school_id}", "SK": "ADVISORY"}
        ).get("Item")
    except Exception as e:
        print(f"api: advisory read failed (falling back): {e}")

    school = next((s for s in seed.SCHOOLS if s["school_id"] == school_id), None)
    lang = (school or {}).get("language", "en")

    tier = int(state["tier"])
    band = state["band"]
    advisory_text = None
    if adv and isinstance(adv.get("text"), dict):
        advisory_text = adv["text"].get(lang) or adv["text"].get("en")

    # Build the body from the allow-list only.
    body = {
        "school_id": school_id,
        "school_name": (school or {}).get("name"),
        "tier": tier,
        "band": band,
        "aqi": state.get("aqi"),
        "advisory": advisory_text or rules.advisory_text(band),
        "advisory_all": (adv or {}).get("text"),
        "advisory_source": (adv or {}).get("source", "computed-fallback"),
        "advisory_generated_at": (adv or {}).get("generated_at"),
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
    return _resp(200, body, origin)
