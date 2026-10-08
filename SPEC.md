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

**AUTHORITATIVE DESIGN — matches the committed diagram (docs/screens/) and the
component contract below. Every later session starts from this section.**

```
[AQI feed: Open-Meteo]                       ┌──────────── S3 + CloudFront (static UI) ──> Principal (dashboard)
        |                                    ^
        v                                    |
[EventBridge: every 15 min]                  |
        |                                    |
        v                                    |
[Lambda ingest: fetch + clean] ──> [DynamoDB: AQI + schools] ──> [API Gateway: Lambda reader]
                                              |
                                              v
                                    [Lambda rules: AQI -> tier]
                                              |
                                              v
                                    [Strands agent: on Bedrock]
                                     (writes+localizes advisory)
                                              |
                                              v
                                    [SNS: dedupe + send] ──> Principal (email alert)
```

Flow: EventBridge fires ingest every 15 min → ingest reads the feed (Open-Meteo,
verified no-key) → writes readings to DynamoDB → rules Lambda reads state, sets the
tier (the ONLY tier setter) → advisory Strands agent localizes the text → SNS dedupes
and emails the principal → API Gateway + CloudFront serve the dashboard.

### Component contract (IAM boundary — least privilege, one table)

| Component | Reads | Writes | IAM boundary |
| --- | --- | --- | --- |
| saans-ingest | feed, snapshot in S3 | `READING#station` items | PutItem on one table, read one S3 prefix |
| saans-rules | readings, school items | `STATE#school` (tier, since, prev_tier) | GetItem, Query, PutItem on one table |
| saans-advisory | state, school | `ADVISORY#school` (en, hi, text) | bedrock:InvokeModel on one model ARN, one table |
| saans-notify | advisory | none | sns:Publish on one topic |
| saans-api | state, advisory | none | read-only on one table |

**Invariant: the rules Lambda is the only thing that sets a tier. (Diagram shows rules -> agent -> SNS as
one chain; in SAM this is one invoke chain.) The tier lives in table `saans-state`.
The advisory Lambda's IAM role has NO write action on `saans-state`, so it is physically unable to set a
tier.**

STATUS: the two-table split (`saans-state` / `saans-content`) is the design that makes this claim
enforceable, and `template.yaml` now exists with the least-privilege policies written. A local IAM
audit of the built template confirms **zero** bare `Action: *` or `Resource: *`: saans-ingest and
saans-rules hold write on `saans-state` only, and saans-api holds **read only**. The claim becomes
*enforced* the moment `sam deploy` creates these roles. Until that deploy runs, this is
"policies written and audited, not yet created in the account" — one notch above design, one notch
below enforced. Do not state it as enforced until the deployed roles are verified with
`aws iam get-role-policy`.

### Storage design — TWO tables so the IAM boundary is literally true

**Why two tables (not one):** with a single table, STATE and ADVISORY share the
partition key `SCHOOL#<id>` and differ only by sort key. DynamoDB's
`dynamodb:LeadingKeys` condition constrains only the partition key, so IAM
**cannot** separate STATE from ADVISORY in one table. We split the tables so the
"advisory can't write STATE" boundary is enforced by IAM, not just by convention.

**saans-state** (the tier lives here — only saans-rules writes it):
- `PK=STATION#<id>, SK=READING#<iso-ts>`: raw AQI, TTL 7 days. (written by saans-ingest)
- `PK=SCHOOL#<id>, SK=PROFILE`: name, station_id, principal_email, language.
- `PK=SCHOOL#<id>, SK=STATE`: tier, aqi, since, prev_tier. (written by saans-rules)

**saans-content** (the words live here — only saans-advisory writes it):
- `PK=SCHOOL#<id>, SK=ADVISORY`: text per language, generated_at, source (bedrock|template).

### IAM boundaries (per the component contract)

- **saans-rules** IAM allows `PutItem/UpdateItem` on saans-state only, and
  `dynamodb:LeadingKeys` pinning its write path. saans-advisory gets **no write
  action on saans-state at all** — the table is a different resource, so it is
  *physically* unable to set a tier. This is the honest, enforceable claim.
- saans-advisory IAM allows `PutItem` on saans-content + `bedrock:InvokeModel`
  on one model ARN + read on saans-state. **No write action on saans-state.**
- saans-notify IAM allows `sns:Publish` on one topic. saans-api: read-only on both.

### Why each service (blog architecture section)

- **EventBridge** — schedule without a server. *Why not cron on a box:* no box to patch.
- **Lambda** — each step small and independently testable. *Why not one big lambda:*
  IAM boundaries + offline unit tests per step.
- **DynamoDB** — state with no ops overhead, two tables (state and content). *Why not RDS:* serverless,
  on-demand, no cluster to babysit at 3 AM.
- **Strands on Bedrock** — writes/localizes the advisory, the one job an LLM adds value.
  *Why not a template for everything:* localization across EN/HI/TE is exactly where an
  LLM earns its keep — but tier stays deterministic.
- **SNS** — delivery with dedup. *Why not SES direct:* managed fan-out + retry.
- **CloudFront + S3** — serves the principal dashboard. *Why not a running server:*
  static, cached, cheap, no ops.

## Build order (matches the diagram, one agent session each)

1. ~~Spec + repo skeleton~~ ✓ (committed e3a0ed1)
2. **Table + seed schools, then saans-rules with tests** (tier setter — do first, it's
   the core invariant)
3. saans-ingest with the snapshot fallback
4. EventBridge wiring, stack in SAM
5. saans-advisory with template fallback, then saans-notify
6. saans-api, then the dashboard
7. Blog + video

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
