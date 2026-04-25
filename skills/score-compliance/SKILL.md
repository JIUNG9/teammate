---
name: score-compliance
description: Score this repository against ISO 27001 + K-ISMS-P. Runs 10 local probes, writes per-control evidence to compliance-vault/, prints a terse table or --json. Pluggable scanner — one of several that write to the teammate vault.
---

# /score-compliance

Run the compliance scanner against the current repository (or a specified path)
and write the results into the team's vault.

## When to invoke

- The user asks "what's our compliance posture?" or "is this repo K-ISMS-P
  compliant?" or "score this".
- Before a release, an audit, or onboarding a new team member.
- As a periodic check (cron, weekly review).

## Behavior

1. Loads catalogs: ISO 27001:2022 Annex A subset (16 controls) + K-ISMS-P
   top 25 controls. The catalog is the moat — first English-language OSS
   to score against K-ISMS-P at all.

2. Runs 10 probes:

   - `codeowners-exists` — `.github/CODEOWNERS` non-empty
   - `branch-protection` — `gh api branches/main/protection` returns 200
   - `secrets-scan` — pattern match for AWS keys, private keys, tokens
   - `tf-state-encryption` — no plaintext `terraform.tfstate` + remote backend
   - `dependency-pinning` — at least one lockfile present
   - `oss-hygiene-workflow` — workflow runs on push/pull_request
   - `pre-commit-config` — `.pre-commit-config.yaml` (or alternative)
   - `license-present` — `LICENSE` file at root
   - `security-md-present` — `SECURITY.md` at root, `.github/`, or `docs/`
   - `dependabot-or-renovate` — config file exists

3. Each probe returns one of: **pass / partial / fail / n/a / indeterminate**.
   `partial` means "local artifact present, but admin scope needed to verify
   the GitHub-side state." Set `GITHUB_TOKEN` with `admin:repo` scope and
   pass `--as-admin` to promote `partial` to `pass` or `fail`.

4. Writes outcomes to `compliance-vault/`:

   - `latest.md` (overwritten every run)
   - `history/<timestamp>.md` (append-only)
   - `controls/iso-27001/<id>.md` (per-control evidence)
   - `controls/k-isms-p/<id>.md` (per-control evidence)
   - `attestations/<timestamp>.pdf` (unsigned preview, or signed if `--sign`)

## Run

```bash
teammate score                    # default: cwd
teammate score /path/to/repo      # specific path
teammate score --json             # machine-readable output
teammate score --quiet            # no table; vault still written
teammate score --sign             # opt-in sigstore keyless signing of the PDF
teammate score --as-admin         # use GITHUB_TOKEN admin scope
```

## Output (default)

```
teammate score — overall: 73.3%  (pass=11 partial=4 fail=0 n/a=0 indet=0)
target: /Users/.../my-team-repo
commit: abc123def

probe                   result                  framework:control       severity
----------------------  ----------------------  ----------------------  ----------------------
codeowners-exists       pass                    iso-27001:A.5.2         medium
codeowners-exists       pass                    k-isms-p:2.1.3          medium
branch-protection       partial                 iso-27001:A.8.32        high
...
```

## What gets stored in the vault

The vault becomes a queryable record of compliance state over time. The
local-LLM `/ask-vault` skill RAGs over this content. Auditors get
markdown they can browse in Obsidian.

## Score formula

`overall = passed / (passed + partial + failed)` as a percentage.
`n/a` and `indeterminate` are excluded from the denominator. `partial`
counts toward denominator but not numerator — incentivizes promoting
partial to pass via `--as-admin`.
