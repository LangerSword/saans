# SAANS — submission writeup (paste-ready)

Draft for the submission form + AWS Builder Center blog. Every claim here is backed by
docs/DEVLOG.md, docs/DECISIONS.md, or docs/screens/ evidence files. Do not add claims that
don't trace to those.

---

**SAANS — School Air Action Notification System** · Air track · solo · Environmental Hacks 2026
Live: https://saans.langersword.in · Repo: https://github.com/LangerSword/saans

**The problem.** On bad-air days, schools improvise. Dashboards show AQI numbers; nothing tells a
principal what to actually change today — move recess indoors, cancel assembly, or close. SAANS
turns the number into the decision.

**What it does.** SAANS reads live air quality for each school's station, converts it to CPCB AQI,
and produces a tier with a deterministic rules engine. The tier drives a short advisory written and
localized (English / Hindi / Telugu) by a Strands agent on Bedrock. When the tier changes, the
principal gets an SNS email — escalations alert immediately, other changes respect a 12-hour
cooldown, and two-reading hysteresis means a boundary flap never spams anyone. A one-page dashboard
shows every school's status, what to do today, and which writer produced the advisory.

**Where AWS fits (the product core, not the deploy destination).**
- **EventBridge → Lambda (five small functions, one job each, hand-scoped IAM).** The advisory
  role has no write action on the state table — the model physically cannot set a tier. The rules
  function is the only tier writer, enforced by IAM, verified by reading the deployed policies back.
- **DynamoDB, two tables** (state / content) so that boundary is an IAM fact, not a convention.
- **Strands Agents SDK on Bedrock** (Nova Lite via a cross-region inference profile) words and
  localizes the advisory. Deterministic EN/HI/TE templates are the fallback, so the alert still
  goes out when the model is throttled — the fallback IS the retry strategy, with a hard
  wall-clock bound on the model call.
- **SNS** delivers with a dedupe policy; **S3 + CloudFront + ACM** serve the dashboard over TLS at
  the custom domain; **API Gateway** fronts a read-only, privacy-hardened API (allow-list
  responses — no contact field can leak; CORS allowlist, never `*`; stage throttling).

**Honest limits, stated inside the product.** The feed is modeled (CAMS, ~11 km grid), not a
station measurement; the index is PM-only; measured misclassification against CPCB's full index
is ~12%. Every advisory carries this disclaimer.

**AI coding tools used.** Hermes Agent (step-5-preview via Nous Research) for the entire build —
driven task-by-task with executable acceptance checks (pytest, live smoke tests). docs/DEVLOG.md
records what it got wrong and how each failure was fixed, including: a SAM changeset bug found
only by a real deploy, DynamoDB float/Decimal rejection, an IAM action-name mismatch proven by a
live AccessDenied, and a Strands-in-Lambda hang fixed with a hard thread bound.
