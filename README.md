# SAANS — School Air Action Notification System

On an AQI-spike day, schools improvise. SAANS reads the air, decides the action tier with a
deterministic rules engine, and tells a school exactly what to do today — in the principal's
language.

Built for **Environmental Hacks** (WeMakeDevs × AWS Builder Center), Air track.

## How it works

```
EventBridge -> Ingest Lambda -> DynamoDB -> Advisory Lambda -> SNS alert + dashboard
```

- **Reads** live air quality (Open-Meteo, no key needed) for each school's nearest station.
- **Decides** the action tier with a pure-Python rules engine — tested offline, no network.
  The tier is always deterministic. The LLM only writes and localizes the advisory text;
  it never changes the tier.
- **Writes** a short advisory (English / Hindi / Telugu) via a Bedrock/Strands agent, with a
  deterministic template fallback if the model is unavailable.
- **Alerts** the school once per tier change (deduped, max once/12h) and shows the status on a
  one-page dashboard.

## Status

Early build. Event window Oct 8–11 2026 — this repo was created Oct 9 2026.

## Stack

AWS (Lambda, DynamoDB, Bedrock/Strands, SNS, API Gateway, S3, CloudFront, EventBridge),
Python. See `SPEC.md` for the data model, tier table, and architecture.
