"""saans-rules Lambda: the ONLY writer of the tier.

Reads the latest reading for a school, applies the tier rules (hysteresis +
staleness), and writes the STATE item that holds the tier. This is the invariant:
the advisory agent can only write advisory text, never the tier.

Fails toward caution: a stale reading never downgrades a tier.
"""
import json
import os


def _table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])


def _latest_reading(table, school_id):
    """Newest READING item for a school, or None."""
    resp = table.query(
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={
            ":pk": f"SCHOOL#{school_id}", ":sk": "READING#"
        },
        ScanIndexForward=False,   # descending -> newest first
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def _current_state(table, school_id):
    resp = table.get_item(Key={"PK": f"SCHOOL#{school_id}", "SK": "STATE"})
    return resp.get("Item")


def _state_from_item(item, aqi):
    """Rebuild a TierState from the persisted STATE item."""
    from core import rules
    if not item:
        return rules.initial_state(aqi)
    return rules.TierState(
        tier=int(item["tier"]),
        band=item["band"],
        aqi=float(aqi),
        prev_tier=item.get("prev_tier"),
        pending_tier=item.get("pending_tier"),
        pending_count=int(item.get("pending_count", 0)),
    )


def handler(event, context=None):
    from core import rules
    table = _table()
    results = []

    school_ids = event.get("school_ids") if isinstance(event, dict) else None
    if not school_ids:
        # Default: every seeded school.
        from core import seed
        school_ids = [s["school_id"] for s in seed.SCHOOLS]

    for school_id in school_ids:
        reading = _latest_reading(table, school_id)
        if reading is None:
            results.append({"school_id": school_id, "skipped": "no reading"})
            continue

        aqi = float(reading["aqi"])
        stale = bool(reading.get("stale", False))
        state_item = _current_state(table, school_id)
        state = _state_from_item(state_item, aqi)

        new_state = rules.next_state_safe(state, aqi, stale=stale)

        # Write the tier. This STATE item is what only saans-rules may write.
        table.put_item(Item={
            "PK": f"SCHOOL#{school_id}",
            "SK": "STATE",
            "tier": new_state.tier,
            "band": new_state.band,
            "aqi": new_state.aqi,
            "prev_tier": new_state.prev_tier,
            "pending_tier": new_state.pending_tier,
            "pending_count": new_state.pending_count,
            "stale_input": stale,
            "breakpoint_version": reading.get("breakpoint_version"),
        })
        results.append({
            "school_id": school_id, "tier": new_state.tier,
            "band": new_state.band, "changed": rules.band_changed(state, new_state),
            "stale_input": stale,
        })

    return {"statusCode": 200, "body": json.dumps({"updated": results})}
