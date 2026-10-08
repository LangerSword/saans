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
