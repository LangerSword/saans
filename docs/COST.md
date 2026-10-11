# SAANS — cost tally

Running spend from AWS Cost Explorer. Update at each deploy + before freeze.

- 2026-10-09: $0.00 (nothing deployed yet; Bedrock quota is the only usage signal, no billable calls yet).
- 2026-10-12: $0.00. First live usage — stack `saans-dev` deployed; ingest/rules/api invoked for the
  smoke test. Cost Explorer daily: 10-09 $0.0000000036 · 10-10 $0.0000000036 · 10-11 $0.0000000018.
  (Lambda + DynamoDB + API Gateway on this volume sit inside free tier.)
