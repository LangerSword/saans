# SAANS — development log

Timestampped entries. After each task, append the block below. This is honest
"what fought back" material for the AWS Builder Center blog.

---

## 2026-10-09T03:05+05:30 — Task 1: spec + repo skeleton

- **Goal:** repo, SPEC contract, DEVLOG, .gitignore, no secrets, in-window commit.
- **What I asked the agent:** scaffold from the build plan; run bounded AQI-source research first.
- **What worked:** Open-Meteo verified no-key live source (Delhi us_aqi 170). Bedrock access
  confirmed enabled in ap-south-1. Repo initialized and pushed to LangerSword/saans in-window.
- **What fought back:** CPCB app.cpcbccr.com dead (404); WAQI demo token returned Shanghai for
  "delhi" — dropped. Bedrock **daily token quota exhausted** (ThrottlingException, not access) —
  so the template fallback carries dev time until quota resets ~08:00 IST. Recorded in SPEC.
- **AWS service used and why:** none yet (local scaffold).
- **Evidence:** commit e3a0ed1 (git log), /tmp/om_delhi.json (feed call), bedrock throttling output.

## 2026-10-09T03:20+05:30 — Authoritative architecture locked

- **Goal:** fold the committed diagram + component contract into SPEC as the single source of truth.
- **What I asked the agent:** read the architecture PNG, transcribe it, and restructure SPEC.
- **What worked:** five-lambda microservice pipeline (ingest/rules/advisory/notify/api) with
  least-privilege IAM boundaries, all captured in SPEC + DECISIONS.
- **What fought back:** diagram shows rules→agent→SNS as one chain; the "rules is the only tier
  setter" invariant needed a real enforcement mechanism, not a convention. First attempt relied
  on IAM against a single table — see the Task 2 entry for why that was wrong.
- **AWS service used and why:** design only — see SPEC "Why each service."
- **Evidence:** docs/screens/ (diagram), SPEC.md architecture section.

## 2026-10-09T03:4x+05:30 — Task 2: rules engine + seed schools

- **Goal:** pure-Python tier engine (the core invariant) + seed data, with pytest green as the
  acceptance check. No AWS calls.
- **What I asked the agent:** implement AQI->band->tier, band-edge tests at 100/101, 200/201,
  300/301, 400/401, two-reading hysteresis on downgrades, and seed schools on different Delhi
  stations. Then fix an IAM overclaim I'd written in SPEC.
- **What worked:** rules.py + test_rules.py — **24/24 tests pass** (evidence:
  docs/screens/pytest-rules.txt). Hysteresis holds downgrades across two readings, adopts
  upgrades immediately, and discards a candidate if AQI rises back. seed.py maps 5 schools
  across 5 distinct Delhi stations so the demo shows different tiers on one day.
- **What fought back:** pytest wasn't in the default interpreter — created an isolated
  `.venv` with uv. Bigger catch: I'd written "IAM gives advisory no write path to STATE, so
  the agent physically can't set a tier" against a *single* table. That's an overclaim —
  `dynamodb:LeadingKeys` only constrains the partition key, and STATE/ADVISORY shared it.
  Fixed by splitting into two tables (saans-state / saans-content) so the IAM claim is
  literally true; recorded the choice in DECISIONS.md.
- **AWS service used and why:** none deployed — rules engine is pure Python, offline-testable.
  (DynamoDB design decided: two tables, see SPEC "Storage design".)
- **Evidence:** docs/screens/pytest-rules.txt, src/core/rules.py, src/core/seed.py.

## 2026-10-09T03:27+05:30 — Task 2 completion: seed tests + doc corrections

- **Goal:** add the missing seed coverage to Task 2 and make the docs state the IAM claim
  exactly as strongly as the design supports it.
- **What I asked the agent:** add pytest coverage for the seed, keep two-reading hysteresis,
  keep band-edge tests, and record the IAM decision properly.
- **What worked:** `tests/test_seed.py` (11 tests) added to the existing 24 — **35 passed**
  (evidence: docs/screens/pytest-rules.txt). Seed invariants now checked: distinct stations,
  coordinates inside Delhi, stations geographically spread, unique school ids, controlled
  principal inbox, supported languages, item shapes, and no STATE item seeded.
- **What fought back:** a test caught a real defect in the seed. `SCHOOLS` had no
  `principal_email` key, but `seed_records()` hardcoded `DEMO_PRINCIPAL` when it wrote items —
  so the seed data and the written records could silently disagree about who gets the alert.
  Fixed by putting `principal_email` on each school and reading it in `seed_records()`.
  Run went 34 passed / 1 failed → 35 passed. Also found two stale "single table" lines
  (SPEC.md and DECISIONS.md) left over from the split, plus a duplicated decision entry and a
  mangled line where my own patch had clobbered the five-lambdas entry. All cleaned.
- **AWS service used and why:** none — offline tests only.
- **Evidence:** docs/screens/pytest-rules.txt (35 passed), tests/test_seed.py,
  src/core/seed.py, SPEC.md, docs/DECISIONS.md.

## 2026-10-09T03:49+05:30 — Task 2 verification + CPCB AQI conversion

- **Goal:** verify Task 2's report against fresh runs, and fix the AQI scale before Task 3.
- **Verification of my own Task 2 claim (per the evidence rule):** `git status` clean,
  `git show --stat eccee7c` confirms tests/test_seed.py and src/core/seed.py are in the commit,
  and a FRESH `.venv/bin/pytest` run (not the saved screenshot) gives the pass count.
  The `principal_email` fix IS fully applied: each school carries the field and
  `seed_records()` reads it. Verified against the committed blob, not the working tree.
- **The scale problem (the important find):** Open-Meteo returns `us_aqi` (US EPA scale) plus raw
  concentrations, and it is CAMS model output — gridded, 11km, not CPCB station monitors. US AQI is
  NOT CPCB AQI. Measured on a live Delhi day, feeding `us_aqi` straight into our CPCB tier table put
  **38% of hours in the wrong tier**. Fixed by computing CPCB AQI ourselves from pm2_5 and pm10.
- **CPCB breakpoints corrected twice against the source.** First attempt used CPCB's calculator
  "Breakpoints" sheet and made bands contiguous — did not reproduce CPCB's own anchors. Read the
  authoritative CPCB National AQI report (Tables 3.5/3.6) and found the bands are each category's OWN
  integer range: (31,60)->(51,100), not (30,60)->(51,100). Now reproduces CPCB's published example
  exactly (31->51, 60->100; CPCB's prose "75 at 45" is rounded, exact is 74.66).
- **Result after the fix:** misclassification drops 38% -> 12% (see docs/screens/scale-check.txt), and
  the remaining 3 are genuine scale differences the conversion now handles. The conversion does real work.
- **PM-only simplification, stated honestly:** CPCB's real rule needs 3+ pollutants including PM; we
  have particulates only, so this is a PM-only index. Documented, not hidden. `test_pm_only_is_a_documented_simplification`
  guards the claim.
- **IAM claim downgraded to design, not fact:** no `template.yaml` exists yet, so "advisory cannot
  write STATE" is a design commitment, enforced when the SAM template lands. Labelled in SPEC.
- **CPCB / data.gov.in feed test (previously unreported):** CPCB app.cpcbccr.com 404, data.gov.in API
  blocked. No live station feed works from here. Open-Meteo is the defensible primary, labelled as
  modeled data in the video and blog.
- **AWS service used and why:** none — offline. (DynamoDB two-table design; IAM enforced at template time.)
- **Evidence:** docs/screens/pytest-rules.txt (71 passed), docs/screens/scale-check.txt,
  tests/test_cpcb_aqi.py (18 tests), src/core/rules.py.
