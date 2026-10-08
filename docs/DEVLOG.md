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
  least-privilege IAM boundaries and single-table DynamoDB, all captured in SPEC + DECISIONS.
- **What fought back:** diagram shows rules→agent→SNS as one chain; enforced the
  "rules is the only tier setter" invariant via IAM (advisory has no write path to STATE).
- **AWS service used and why:** design only — see SPEC "Why each service."
- **Evidence:** docs/screens/ (diagram), SPEC.md architecture section.
