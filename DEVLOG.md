# SAANS DEVLOG

Append three lines after each task: what I asked the agent, what it got wrong, how I fixed it.
(This is honest "what fought back" material for the Builder Center blog.)

## 2026-10-09

- **Task 1 — Spec + repo skeleton.** Asked step-5-preview (max reasoning) to scaffold SPEC/DEVLOG/gitignore from the build plan. Ran the bounded AQI-source research first per plan §9.
- **Got right:** Open-Meteo verified as the no-key source (Delhi live us_aqi 170). Bedrock access confirmed enabled in ap-south-1. Repo initialized in-window.
- **Got wrong / fixed:** CPCB app.cpcbccr.com is dead (404); WAQI demo token returned Shanghai, China for "delhi" — wrong station, dropped. Discovered Bedrock daily token quota is exhausted (not an access problem) — so the deterministic-template fallback isn't optional, it carries dev time until quota resets ~08:00 IST. Recorded this in SPEC so it doesn't surprise Task 5.
