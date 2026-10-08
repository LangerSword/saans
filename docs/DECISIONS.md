# SAANS — decisions log

One short entry per choice: "Chose X over Y because Z." Append as decisions are made.
Used by the blog protocol — Hermes drafts blog sections from DEVLOG.md + DECISIONS.md only.

## 2026-10-09

- **Chose Open-Meteo over CPCB/WAQI/OpenAQ because** the others are dead (CPCB 404),
  connection-blocked (data.gov.in), need an API key (OpenAQ), or return the wrong station
  (WAQI demo token → Shanghai for "delhi"). Open-Meteo is no-key, live, works for Delhi.
  Trade-off: it's CAMS model output, not a raw CPCB station — state this honestly in the blog.
- **Chose Delhi over Hyderabad because** both feeds returned clean recent data, and Delhi
  has denser coverage + bigger spike days for the story. Language is a per-school setting,
  so Telugu schools still fit.
- **Chose deterministic template fallback over a second LLM because** a second provider adds
  setup and another thing to debug without improving the demo. If Bedrock is down or throttled,
  the tier still decides and the alert still sends.
- **Chose DynamoDB (two tables) over relational because** no ops overhead, serverless,
  on-demand — nothing to babysit during a 4-day event.
- **Chose two DynamoDB tables (saans-state / saans-content) over one single table because**
  with a single table, STATE and ADVISORY share the partition key `SCHOOL#<id>` and differ
  only by sort key; `dynamodb:LeadingKeys` constrains only the partition key and so cannot
  separate them. Splitting makes "the advisory lambda cannot write STATE" a literally-true
  IAM claim rather than an overclaim. Cheap now, expensive to retrofit later.
  The alternative (one table + "code path never writes STATE, enforced by a test") was
  rejected as weaker — judges/readers who check the policy would catch the overclaim.
- **Chose five small lambdas over one big lambda because** each step is independently
  testable and IAM boundaries are enforceable per step (rules is the only tier setter).
- **Chose two-reading hysteresis on downgrades (not upgrades) because** upgrades are safety
  events and must alert immediately; downgrades that flapped at a band boundary would spam the
  principal with repeat alerts at ~100/101/200 boundaries.
- **Chose seed schools on DIFFERENT Delhi stations because** the demo needs to show different
  tiers on the same day, which a single city-average feed can't produce.
- **Chose to compute CPCB AQI from concentrations (not feed us_aqi in) because** US AQI is not CPCB
  AQI. Measured on a live Delhi day, us_aqi put 38% of hours in the wrong CPCB tier; computing CPCB
  AQI from pm2_5/pm10 with CPCB's own breakpoints drops that to 12%, and the remaining gap is a real
  scale difference, not a bug. Anchor values are CPCB's own published example, asserted in tests.
- **Chose Open-Meteo (CAMS model, labeled as modeled) as primary because** no live station feed is
  reachable (CPCB 404, data.gov.in blocked). It is gridded model output, not CPCB monitors, and the
  blog and video say so. PM-only index is a documented simplification, not the full CPCB 3-pollutant index.
- **Chose to downgrade the IAM "cannot write STATE" claim to DESIGN (not fact) because** no
  template.yaml exists yet, so no policy is created. It becomes a fact when the SAM template lands and
  the policy is verified. Overclaiming it now would be exactly the failure the two-table split was meant
  to prevent.
