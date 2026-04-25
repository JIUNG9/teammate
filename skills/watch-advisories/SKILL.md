---
name: watch-advisories
description: Diff KISA RSS + NVD CVE feeds against last run, write new items into compliance-vault/advisories/. Pluggable scanner — keeps the vault current with external security knowledge so the local-LLM ask-vault skill can answer "what changed this week?" questions.
---

# /watch-advisories

External security knowledge as a first-class vault citizen. Where
`/score-compliance` captures internal state, this skill captures the
moving target outside.

## When to invoke

- Weekly cron / Monday morning routine.
- The user asks "what's new in security this week?", "any new CVEs that
  affect us?", "what KISA notices came out?".
- Automatically: `teammate ask` answers freshen up after a `watch` run.

## Behavior

1. Pulls feeds in parallel:

   - **KISA RSS** (https://www.kisa.or.kr/rss/notice.xml) via `feedparser`.
     Korean-language. Public. No API key.
   - **NVD CVE 2.0 API** for the last 7 days (configurable via `--days`).
     English. Unauthenticated, but NVD asks for a `User-Agent` (we send one).

2. Diffs each feed against the per-source state stored in
   `compliance-vault/.teammate-watch-state.json`. Only NEW items since
   last run are emitted.

3. Writes:

   - `compliance-vault/advisories/<timestamp>.md` — full diff with each
     new item's title, link, published date, and 300-char summary
   - `compliance-vault/history/<timestamp>-advisory.md` — one-line
     summary entry pointing at the advisories file

4. Caps stored seen-id list at 500 per source so the state file doesn't
   grow unbounded.

## Run

```bash
teammate watch                      # all sources (KISA + NVD)
teammate watch --source kisa        # only KISA
teammate watch --source nvd --days 14   # NVD lookback over 2 weeks
```

## Output

```
kisa: fetched=12 new=3 — first new: 보안공지: ...
nvd: fetched=187 new=42 — first new: CVE-2026-0815
```

## What this is NOT

- Not a vulnerability scanner — doesn't check whether your stack is
  affected. It surfaces what's out there. Pair with `/score-compliance`
  + your team's CVE/SBOM tooling for the matching layer.
- Not a real-time stream — it's a polled diff. Re-run when you want
  fresh state.

## Privacy

KISA + NVD are public feeds; teammate fetches them directly. Your query
shape is "give me everything in the window" — not specific to your
codebase. Nothing leaves your laptop except the feed fetch itself.
