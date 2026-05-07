# Memory import draft — alice — 2026-05-07

Default for every entry below is **SKIP**. To import an entry, edit this file and check its `[ ] IMPORT THIS` box. Save your preferred redactions inline. The CLI never auto-imports — your checkmark is the only thing that lands the entry.

- Source memory root: `/Users/alice/.claude`
- Target brain root: `/srv/team-brain`
- Entries surfaced: 5  (flagged for redaction: 1)

---

## Team rules — third-person conventions (1)

### Entry 1 — TEAM_RULE

- [ ] IMPORT THIS
- Source: `MEMORY.md` line 14
- Original: we deploy via ArgoCD on every merge to main
- Redaction flags: none

## Team facts — concrete claims (2)

### Entry 2 — TEAM_FACT

- [ ] IMPORT THIS
- Source: `MEMORY.md` line 22
- Original: Auth service owner is alice; on-call rotation in PagerDuty
- Redaction flags: none

### Entry 3 — TEAM_FACT

- [ ] IMPORT THIS
- Source: `MEMORY.md` line 31
- Original: Production cluster runs Kubernetes 1.33; metrics live at db01.prod.internal:9090
- Redaction flags: contains internal-looking hostname
- Suggested redactions: replace flagged values with generic placeholders before checking the box.

## References — pointers to external resources (1)

### Entry 4 — REFERENCE

- [ ] IMPORT THIS
- Source: `MEMORY.md` line 47
- Original: see Linear project AUTH-2026-Q2 for the migration plan
- Redaction flags: none

## Personal — surfaced for completeness; almost never imports (1)

### Entry 5 — PERSONAL

- [ ] IMPORT THIS
- Source: `MEMORY.md` line 9
- Original: I prefer dark mode for everything
- Redaction flags: none

---

_When you're done, commit only this file. The brain's CI will diff it against future commits to show what landed and what didn't. Drafts live under `pending-imports/` and are gitignored by default — remove the entry from `.gitignore` if your team wants the draft itself in PR review._
