"""saans-advisory Lambda: words and localizes the advisory; never sets a tier.

Reads the STATE item (tier/band, written only by saans-rules), asks Bedrock
(Strands Agents SDK) to phrase + translate the fixed action into EN/HI/TE, and
writes the ADVISORY item to saans-content. Deterministic templates are the
fallback — same action, same disclaimer — so an alert always goes out even
when the model is throttled or down.

IAM: this role has NO write action on saans-state. The tier physically cannot
be changed from here. The alert-state fields (alerted_at, delivered) are
carried forward from the previous ADVISORY item; only saans-notify updates
them when it actually sends.
"""
import json
import os
import threading
import time

DEFAULT_MODEL_ID = "apac.amazon.nova-lite-v1:0"


def _tables():
    import boto3
    ddb = boto3.resource("dynamodb")
    return ddb.Table(os.environ["STATE_TABLE"]), ddb.Table(os.environ["CONTENT_TABLE"])


def _bedrock_text(prompt: str) -> str:
    """One-shot advisory wording via the Strands Agents SDK on Bedrock.

    The boto_client_config is load-bearing: without it, botocore retries a
    quota ThrottlingException with long backoff until the Lambda's own timeout
    kills the run (found by the T5 smoke — 60s timeouts, nothing logged).
    One attempt, tight timeouts: the template fallback IS the retry strategy.
    """
    from botocore.config import Config as BotocoreConfig
    from strands import Agent
    from strands.models import BedrockModel

    from core import advisory

    model = BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID),
        region_name=os.environ.get("BEDROCK_REGION", "ap-south-1"),
        boto_client_config=BotocoreConfig(
            connect_timeout=5,
            read_timeout=20,
            retries={"max_attempts": 1, "mode": "standard"},
        ),
    )
    agent = Agent(model=model, system_prompt=advisory.SYSTEM_PROMPT, callback_handler=None)
    return str(agent(prompt))


def _bedrock_text_guarded(prompt: str, seconds: int = 20) -> str:
    """_bedrock_text with a hard wall-clock bound.

    The T5 smoke found the SDK can hang far past its own timeouts inside the
    Lambda (120s of silence, no logs, both with and without boto retry config).
    A daemon thread + join bound guarantees the alert path moves on: the
    template fallback IS the retry strategy.
    """
    result: dict = {}

    def _run():
        try:
            result["text"] = _bedrock_text(prompt)
        except Exception as e:  # surfaced to the caller below
            result["error"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError(f"bedrock call still running after {seconds}s")
    if "error" in result:
        raise result["error"]
    return result["text"]


def _generate(school: dict, band: str) -> dict:
    """Return {"source", "text", "note"} — never raises; templates on any doubt."""
    from core import advisory, rules

    action_en = rules.ACTIONS.get(band, rules.ACTIONS["moderate"])
    try:
        print(f"advisory: bedrock call start for {school['school_id']}")
        raw = _bedrock_text_guarded(
            advisory.build_user_prompt(band, action_en, school["name"], "Delhi")
        )
        print(f"advisory: bedrock returned {len(raw)} chars for {school['school_id']}")
        parsed = advisory.parse_model_json(raw)
        if parsed:
            return {"source": "bedrock", "text": parsed, "note": None}
        return {"source": "template", "text": advisory.all_templates(band),
                "note": "model reply unparsable; template used"}
    except Exception as e:  # quota, network, anything — the alert must still go out
        # Log the full error: the smoke test proved that the exception TYPE alone
        # (AccessDeniedException vs ThrottlingException) is not enough to debug
        # which action/resource was refused.
        print(f"advisory: bedrock failed for {school['school_id']}: {type(e).__name__}: {e}")
        return {"source": "template", "text": advisory.all_templates(band),
                "note": f"bedrock unavailable: {type(e).__name__}"}


def handler(event, context=None):
    from core import advisory, ddb, seed

    state_t, content_t = _tables()
    by_id = {s["school_id"]: s for s in seed.SCHOOLS}
    school_ids = (event or {}).get("school_ids") or list(by_id)
    now = int(time.time())
    # Hard deadline: never let model latency eat the whole run. Past it, the
    # remaining schools get templates — the alert path must not be hostage to
    # a slow model.
    deadline = time.time() + 90
    results = []

    for sid in school_ids:
        school = by_id.get(sid)
        if not school:
            results.append({"school_id": sid, "skipped": "unknown school"})
            continue
        st = state_t.get_item(Key={"PK": f"SCHOOL#{sid}", "SK": "STATE"}).get("Item")
        if not st:
            results.append({"school_id": sid, "skipped": "no state"})
            continue

        prev = content_t.get_item(Key={"PK": f"SCHOOL#{sid}", "SK": "ADVISORY"}).get("Item") or {}
        band, tier = st["band"], int(st["tier"])
        if time.time() > deadline:
            gen = {"source": "template", "text": advisory.all_templates(band),
                   "note": "deadline guard: template"}
        else:
            gen = _generate(school, band)

        item = {
            "PK": f"SCHOOL#{sid}",
            "SK": "ADVISORY",
            "tier": tier,
            "band": band,
            "text": gen["text"],
            "source": gen["source"],
            "model_id": os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
            if gen["source"] == "bedrock" else None,
            "generated_at": now,
            # carry the alert-state forward; only saans-notify updates these.
            # None-safe: DynamoDB NULLs come back as None and int(None) killed
            # the first full run (found in the T5 smoke).
            "prev_tier": int(prev["tier"]) if prev.get("tier") is not None else None,
            "alerted_at": int(prev["alerted_at"]) if prev.get("alerted_at") is not None else None,
            "delivered": bool(prev.get("delivered", False)),
        }
        content_t.put_item(Item=ddb.to_ddb(item))
        results.append({"school_id": sid, "source": gen["source"], "band": band,
                        "note": gen["note"]})

    # Chain: nudge notify (async, best-effort). The advisory is already stored.
    for_next = [r["school_id"] for r in results if "skipped" not in r]
    if for_next:
        try:
            import boto3
            fn = os.environ.get("NOTIFY_FUNCTION")
            if fn:
                boto3.client("lambda").invoke(
                    FunctionName=fn, InvocationType="Event",
                    Payload=json.dumps({"school_ids": for_next}),
                )
        except Exception as e:
            print(f"advisory: notify invoke failed: {e}")

    return {"statusCode": 200, "body": json.dumps({"advisories": results})}
