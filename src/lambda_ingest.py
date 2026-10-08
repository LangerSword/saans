"""saans-ingest Lambda: fetch readings, compute CPCB AQI, write readings to state.

Invoked hourly by EventBridge. Kept OUT of a VPC so it reaches Open-Meteo with
no NAT cost. Every reading carries provenance; nulls stay None (never 0, which
would read as Good air); the newest reading's staleness is recorded so the rules
step can fail toward caution.

The TIER is not set here — that is saans-rules' job, and only saans-rules holds a
STATE write for the tier key. Ingest lands raw readings plus the computed AQI.
"""
import json
import os
import time


def _table():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])


def handler(event, context=None):
    # Imported here (not at module top) so unit tests of the pure core never need
    # boto3, and so a missing dep fails fast at invoke, not at cold import.
    from core import ingest, rules, seed

    table = _table()
    wrote = 0
    summary = []

    for school in seed.SCHOOLS:
        station = seed.STATIONS[school["station_id"]]
        try:
            readings = ingest.fetch_reading(
                school["school_id"], station["lat"], station["lon"]
            )
        except Exception as e:  # one school's feed failure must not abort the run
            print(f"ingest: fetch failed for {school['school_id']}: {e}")
            continue

        latest = ingest.latest_reading(readings)
        if latest is None:
            continue
        # A reading with neither particulate carries no information; skip it.
        if latest.pm2_5 is None and latest.pm10 is None:
            continue

        stale = ingest.is_stale(latest)
        aqi, dominant = rules.aqi_from_pm(latest.pm2_5, latest.pm10)
        band = rules.aqi_to_band(aqi)

        item = {
            "PK": f"SCHOOL#{school['school_id']}",
            "SK": f"READING#{latest.timestamp_utc}",
            **json.loads(latest.to_json()),   # source, modeled, raw pm2_5/pm10, bp version
            "aqi": aqi,
            "dominant_pollutant": dominant,
            "band": band,
            "stale": stale,
            "ttl": int(time.time()) + 7 * 24 * 3600,   # raw readings expire in 7 days
        }
        table.put_item(Item=item)
        wrote += 1
        summary.append({
            "school_id": school["school_id"], "aqi": aqi, "band": band,
            "stale": stale, "dominant": dominant,
        })

    return {"statusCode": 200, "body": json.dumps({"wrote": wrote, "readings": summary})}
