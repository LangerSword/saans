# SAANS — demo video shotlist (≤3:00, recorded, YouTube public/unlisted)

The video is what judges see. Three beats: problem & user → live build → AWS spine.
Screen-record the dashboard + terminal; voiceover optional (captions are fine).

## Before recording (checklist)

- [ ] SNS email confirmed (subscription shows a real ARN, not PendingConfirmation).
- [ ] Bedrock retest: `aws bedrock-runtime invoke-model --region ap-south-1 --model-id apac.amazon.nova-lite-v1:0 ...` — if still `Too many tokens per day`, that's OK: the video says "model path wired; fallback carries the alert" and the badge shows `advisory: template`. Retest ~08:00 IST; use live Bedrock if it works.
- [ ] Dashboard loaded once (warm), `https://saans.langersword.in`.
- [ ] Reset demo school: `aws dynamodb delete-item --table-name saans-state-dev --key '{"PK":{"S":"SCHOOL#sch-005"},"SK":{"S":"STATE"}}'` (makes the chain fire on camera).
- [ ] Have this file + a terminal open.

## Beat 1 — Problem & user (0:00–0:30)

- Show the dashboard. Line: "On bad-air days, schools improvise. This is what a principal sees
  today: each school, its tier, and exactly what to do — in their language."
- Point at one school: `moderate · AQI 128` + the advisory text + `advisory: template` badge.

## Beat 2 — Live build / the chain (0:30–2:00)

- Terminal (paste-ready, run in order):
  ```
  cd ~/projects/saans && export AWS_DEFAULT_REGION=ap-south-1
  aws lambda invoke --function-name saans-rules-dev --payload '{}' /tmp/r.json --cli-read-timeout 200 && cat /tmp/r.json
  ```
  Say: "I deleted this school's state — the rules engine is the only writer of a tier, and it
  just rebuilt it. Watch the chain: rules → advisory → notify → SNS."
- Show the ADVISORY item regenerated (source + generated_at) and the notify receipt:
  ```
  aws dynamodb get-item --table-name saans-content-dev --key '{"PK":{"S":"SCHOOL#sch-005"},"SK":{"S":"ADVISORY"}}' --query "Item.{source:source.S,alerted_at:alerted_at.N,delivered:delivered.BOOL}" --output json
  ```
- Refresh the dashboard; switch language tabs (English → हिन्दी → తెలుగు).
- If SNS confirmed: show the alert email arriving.

## Optional: simulated spike (the Moderate→Poor flip — say "simulating a spike" on camera)

```
# 1. Write a synthetic Poor-level reading for sch-005 (labeled: simulated-for-demo)
aws dynamodb put-item --table-name saans-state-dev --item '{"PK":{"S":"SCHOOL#sch-005"},"SK":{"S":"READING#2026-10-13T01:00"},"aqi":{"N":"255"},"band":{"S":"poor"},"stale":{"BOOL":false},"source":{"S":"simulated-for-demo"},"modeled":{"BOOL":true},"breakpoint_version":{"S":"cpcb-naqi-2014-pm-v1"},"ttl":{"N":"1792400000"}}'
# 2. Run the chain — escalations adopt immediately (no hysteresis on upgrades)
aws lambda invoke --function-name saans-rules-dev --payload '{}' /tmp/r.json --cli-read-timeout 200 && cat /tmp/r.json
# 3. Refresh the dashboard: sch-005 flips to poor (red), advisory regenerates, alert sends.
# 4. Cleanup after recording:
aws dynamodb delete-item --table-name saans-state-dev --key '{"PK":{"S":"SCHOOL#sch-005"},"SK":{"S":"READING#2026-10-13T01:00"}}'
```

## Beat 3 — AWS spine (2:00–2:45)
- Console (or terminal) tour, fast cuts: EventBridge rule (hourly) → the five Lambdas → DynamoDB
  tables (saans-state / saans-content) → Bedrock model (Nova Lite profile) → SNS topic →
  CloudFront distribution. Overlay `docs/screens/architecture.png`.
- One line per service, why it's there (from SPEC "Why each service").
- Mention the IAM boundary: "the advisory Lambda has no write action on the state table — the
  model physically cannot set a tier."

## Beat 4 — Close (2:45–3:00)

- Back to the dashboard. "A small problem solved well: the principal knows what to do before
  the first bell. Live at saans.langersword.in."

## After recording

- Upload to YouTube: public or unlisted. Check the link opens in a signed-out browser
  (`curl -sI` + incognito).
- Add the link to the submission form + writeup (docs/WRITEUP.md).
