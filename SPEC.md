# SAANS — School Air Action Notification System

**Environmental Hacks** (WeMakeDevs × AWS Builder Center), Air track, solo.
Event window: Oct 8–11 2026. Repo created Oct 9 2026 (in-window).

## One-line pitch

On an AQI-spike day, schools improvise. SAANS reads the air, decides the tier with
a deterministic rules engine, and tells a school exactly what to do today — in the
principal's language.

## The rule that keeps this honest

**The tier is ALWAYS decided by the rules engine (pure Python, tested offline).
The LLM only writes and localizes the advisory text. The LLM never changes the
tier.** This is what makes the whole thing testable without a network and safe if
Bedrock is down.

## Data model

- **Reading**: `{station, city, aqi_us, pm2_5, pm10, ts}` — one per poll per station.
- **School**: `{school_id, name, city, nearest_station, principal_email, language}`.
- **State**: `{school_id, current_tier, tier_entered_ts, last_alert_ts, advisory}`.
  Persisted in DynamoDB. Dedup: re-alert on **tier change** or **escalation**,
  max **once per 12h** per school.

## AQI source (verified 2026-10-09)

**Open-Meteo** `https://air-quality-api.open-meteo.com/v1/air-quality`
- No API key. Live current + hourly forecast. Non-commercial free, attribution required.
- Verified: Delhi us_aqi 170 (pm2_5 87.1) @ 02:30 IST; Hyderabad 91.
- NOTE: Open-Meteo is CAMS model output, not a raw CPCB station — state this honestly
  in the writeup/blog.
- Fallback if the live call fails: serve the last cached snapshot from DynamoDB,
  stamped with its age.

## Tier table (CPCB bands; school actions are OUR draft — verify before blog)

| AQI (US) | Band | Action |
| --- | --- | --- |
| 0–100 | Good/Satisfactory | Normal day |
| 101–200 | Moderate | Sensitive students (asthma) limit exertion |
| 201–300 | Poor | PE/recess indoors, no outdoor assembly, mask advisory |
| 301–400 | Very Poor | Indoor only, shorten day / hybrid, notify parents |
| 401+ | Severe | Recommend closure / online classes, escalate to authorities |

Band edges under test: 50/51, 100/101, 200/201, 300/301, 400/401.

## Architecture (deployed-first on AWS, ap-south-1)

```
EventBridge (sched)  ->  Ingest Lambda  ->  DynamoDB (readings)
                                                    
                         Advisory Lambda (Strands agent on Bedrock)
                              input: tier + school  (tier from rules engine)
                              output: short advisory EN/HI/TE
                              fallback: deterministic template if Bedrock down

                         Alert: SNS email  (dedup in DynamoDB state)

                         API Gateway -> Dashboard: S3 + CloudFront (static page)
```

- **Ingest Lambda**: fetch Open-Meteo per station, normalize, write DynamoDB.
  Cached-snapshot fallback on failure.
- **Advisory Lambda**: Bedrock/Strands localizes the advisory. Tier stays deterministic.
  Deterministic EN/HI/TE templates are the fallback (not a second LLM).
- **Seed**: 5–10 Delhi schools (name, nearest station, principal email, language).
  Principal emails are OUR controlled addresses (SNS email endpoints must confirm
  subscription — never point at a real school).
- **UI**: one static page — big color status, "what to do today", last-updated time.

## AWS footprint (must be visible in the demo video)

EventBridge + Lambda + DynamoDB + Bedrock/Strands + SNS + S3 + CloudFront + API GW.
ap-south-1. Free-tier / credit-bounded. Teardown after submit.

## Scoring target (from First Commit 25/30 teardown)

AWS Usage 8→10 (Bedrock/Strands as product core, not just deploy dest) ·
Video 3→4 (scripted 3-min, AWS visible) · Design 3→4 (one primary action) ·
Idea/Impact 7→8 (schools/parents + hard numbers) · Execution hold at 4/4.

## Task pack (one agent session each)

1. Spec + repo skeleton (this) ✓
2. Rules engine (pure Python) + band-edge tests
3. Ingest Lambda + cached-snapshot fallback
4. Seed script (5–10 Delhi schools)
5. Advisory Lambda (Strands/Bedrock + deterministic fallback)
6. Alert path (SNS email + dedup)
7. API + dashboard (single static page)
8. SAM template + deploy + CloudFront + domain

## Known constraints (verified)

- Bedrock access: ENABLED in ap-south-1. Daily token quota exhausted at capture
  (resets ~08:00 IST). Deterministic fallback will carry dev until then.
- strands-agents SDK: not yet installed — Task 5 installs it.
- SNS email endpoints need confirmation click before they receive.
