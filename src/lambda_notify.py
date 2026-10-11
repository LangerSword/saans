"""saans-notify Lambda: the only thing that sends.

Reads the ADVISORY item, applies the dedupe policy (escalation sends at once;
other changes respect a 12h cooldown), publishes to SNS, then writes the
delivery receipt (alerted_at, delivered) back onto the ADVISORY item in
saans-content. It holds NO write action on saans-state — it can never touch
a tier.
"""
import json
import os
import time


def handler(event, context=None):
    import boto3

    from core import ddb, notify, seed

    content = boto3.resource("dynamodb").Table(os.environ["CONTENT_TABLE"])
    sns = boto3.client("sns")
    topic = os.environ["SNS_TOPIC_ARN"]
    dash = os.environ.get("DASHBOARD_URL", "https://saans.langersword.in")
    by_id = {s["school_id"]: s for s in seed.SCHOOLS}
    now = int(time.time())
    results = []

    for sid in (event or {}).get("school_ids") or list(by_id):
        school = by_id.get(sid)
        raw = content.get_item(Key={"PK": f"SCHOOL#{sid}", "SK": "ADVISORY"}).get("Item")
        if not school or not raw:
            results.append({"school_id": sid, "sent": False, "reason": "no advisory"})
            continue

        item = ddb.from_ddb(raw)  # Decimals -> int/float for pure logic
        prev_tier = item.get("prev_tier")
        prev = None if prev_tier is None else {
            "tier": prev_tier, "alerted_at": item.get("alerted_at") or 0,
        }
        should, reason = notify.alert_decision(prev, int(item["tier"]), now)
        if not should:
            results.append({"school_id": sid, "sent": False, "reason": reason})
            continue

        subject, body = notify.sns_message(school, item, dash)
        sns.publish(TopicArn=topic, Subject=subject[:100], Message=body)
        content.update_item(
            Key={"PK": f"SCHOOL#{sid}", "SK": "ADVISORY"},
            UpdateExpression="SET alerted_at = :a, delivered = :d",
            ExpressionAttributeValues={":a": now, ":d": True},
        )
        results.append({"school_id": sid, "sent": True, "reason": reason})

    return {"statusCode": 200, "body": json.dumps({"notify": results})}
