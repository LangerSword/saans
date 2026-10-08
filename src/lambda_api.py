"""saans-api Lambda: read-only dashboard backend.

Returns a school's current STATE plus its latest reading, with provenance so the
dashboard can show the estimate disclaimer and attribution. This function holds
a DynamoDB READ policy only — no write action on saans-state, which is what makes
the "advisory/API cannot set a tier" boundary an IAM fact, not a convention.
"""
import json
import os


def _table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            # The dashboard is served from the same origin in the demo; keep CORS
            # open for local development only, tighten before any real use.
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }


def handler(event, context=None):
    from core import rules
    table = _table()

    school_id = (event.get("pathParameters") or {}).get("school_id")
    if not school_id:
        return _resp(400, {"error": "school_id is required"})

    state = table.get_item(Key={"PK": f"SCHOOL#{school_id}", "SK": "STATE"}).get("Item")
    if not state:
        return _resp(404, {"error": f"no state for {school_id}"})

    # Latest reading, for provenance and the raw numbers behind the tier.
    r = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={":pk": f"SCHOOL#{school_id}", ":sk": "READING#"},
        ScanIndexForward=False, Limit=1,
    ).get("Items", [])
    reading = r[0] if r else None

    tier = int(state["tier"])
    band = state["band"]
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
            "timestamp_utc": reading.get("timestamp_utc"),
            "pm2_5": reading.get("pm2_5"),        # None means no reading, not zero
            "pm10": reading.get("pm10"),
            "aqi": reading.get("aqi"),
            "dominant_pollutant": reading.get("dominant_pollutant"),
            "source": reading.get("source"),
            "modeled": reading.get("modeled"),
            "stale": reading.get("stale", False),
        }
    return _resp(200, body)
