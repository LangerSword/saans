# Deploy runbook (SAANS deployed slice)

**Only you run `sam deploy`.** Everything below `sam deploy` is prepared and validated locally;
the deploy itself is the one irreversible, cost-touching step.

## What this deploys

EventBridge (hourly) → **saans-ingest** → DynamoDB **saans-state** → **saans-api** (read-only).
Advisory and SNS are NOT in this slice; they bolt on after, and advisories already fall back to
templates. Region **ap-south-1**. Lambdas stay **out of a VPC** (no NAT cost; Open-Meteo needs
outbound internet, which default Lambda networking provides).

## Pre-deploy checklist (done locally)

- [x] `sam validate` — template is valid.
- [x] `sam build` — all three handlers package.
- [x] IAM audit of the built template — **zero** bare `Action: *` or `Resource: *`.
      ingest + rules: write on `saans-state` only. api: **read only**.
- [x] Open-Meteo reachable (HTTP 200) — confirms the no-VPC path works.
- [x] Core (`core/`) is pure stdlib; handlers import boto3 at invoke, not at import.

## Before you deploy — verify these in the account

1. **Account + budget.** Account `703651068111` is confirmed via `aws sts get-caller-identity`.
   Budget alarms already exist ($10 "My Monthly Cost Budget" and $15 GPU desk; actual spend $1.53).
   If you want a $1 alarm for this stack, create one in Billing → Budgets first.
2. **Region.** Set `ap-south-1`: `export AWS_DEFAULT_REGION=ap-south-1` (no default region is
   currently configured on this machine).
3. **Read the IAM statements** in `template.yaml` before deploying (they are in the file; the
   audit above is a summary, not a substitute for reading them).

## Deploy

```bash
cd ~/projects/saans
export AWS_DEFAULT_REGION=ap-south-1
export SAM_CLI_TELEMETRY=0
~/.local/bin/sam deploy --guided \
  --stack-name saans-dev \
  --region ap-south-1 \
  --capabilities CAPABILITY_IAM \
  --resolve-s3
```

`--guided` prompts for a bucket and confirms before creating. Answer the prompts, let it create the
stack, and copy the **ApiUrl** from the outputs.

## After deploy — make the IAM claim true

```bash
# verify the api role truly has no write action on saans-state
aws iam list-attached-role-policies --role-name <saans-api role>
aws iam get-role-policy --role-name <saans-api role> --policy-name <policy>
```

Only after you read the deployed policy and confirm no write action, update SPEC from
"policies written and audited" to **enforced**.

## Smoke test

```bash
# trigger ingest once (don't wait for the hourly schedule)
aws lambda invoke --function-name saans-ingest-dev /tmp/out.json && cat /tmp/out.json
# then rules
aws lambda invoke --function-name saans-rules-dev /tmp/out.json && cat /tmp/out.json
# then read the dashboard API
curl "$API_URL/state/sch-001"
```

## Teardown (cost hygiene)

```bash
aws cloudformation delete-stack --stack-name saans-dev --region ap-south-1
```

## Fallback if deploy hits a wall late Saturday

`sam local invoke` with DynamoDB Local still counts as using AWS open-source tooling (SAM, the
DynamoDB Local endpoint). Treat it as a fallback only — a real deployed URL scores better and is
more convincing in the video.
