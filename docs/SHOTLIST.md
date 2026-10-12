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
