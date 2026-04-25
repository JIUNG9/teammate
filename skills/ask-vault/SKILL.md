---
name: ask-vault
description: Ask a question about the team's compliance state, advisories, or tribal knowledge. Streams an answer from a local LLM (Ollama) grounded in the compliance-vault/, the team's CLAUDE.md, and the team's docs/. Falls back to keyword search if Ollama isn't running.
---

# /ask-vault

The headline pillar. The new SRE on day 1 can ask the team's vault questions
and get a grounded answer from a local LLM running on their laptop.

## When to invoke

- The user asks a question about compliance state, audit history, recent
  advisories, or "what does our team do for X?"
- Examples that should route here:
  - "What's our K-ISMS-P score right now?"
  - "Which ISO 27001 controls are failing?"
  - "What CVEs hit our stack this week?"
  - "What's the team's terraform deployment process?"
  - "Who owns the auth-service repo?"

## Behavior

1. Indexes (or re-uses the existing index of) every `.md` under
   `compliance-vault/`, the team's root `CLAUDE.md`, `docs/`, and `README.md`.
   The index lives in `.teammate-cache/vault.sqlite`.

2. Embeds the user's query via Ollama (`nomic-embed-text` by default) and
   runs cosine similarity against the indexed chunks.

3. Falls back to BM25-ish keyword scoring if Ollama isn't running OR no
   embeddings exist for any chunks.

4. Builds a context block of the top-k chunks (default 6) and streams an
   answer from Ollama (`llama3.2:3b` by default). System prompt enforces:

   - Cite file paths in `[brackets]` for every fact
   - Refuse to make up control IDs / framework names / evidence
   - Use Korean compliance terms (K-ISMS-P, KISA, 개인정보) without apology
   - Be terse; engineers don't need preamble

5. If Ollama isn't running, returns the matching file paths instead of a
   synthesized answer. Tells the user how to start Ollama.

## Run

```bash
teammate ask "what's our current K-ISMS-P posture?"
teammate ask "which controls failed in the last score run?"
teammate ask --top-k 10 "summarize the CVEs from this week's watch run"
teammate ask --rebuild "force a re-index, then answer"
```

## Output (Ollama running)

```
The most recent score run (2026-04-26 10:30 UTC, commit abc123) shows
73.3% overall. Failing probes [compliance-vault/latest.md]:

  - branch-protection: partial — needs admin token to verify [compliance-vault/controls/iso-27001/A.8.32.md]
  - tf-state-encryption: partial — remote backend declared, encrypt=true not found [compliance-vault/controls/k-isms-p/2.7.4.md]
  ...

To promote partial results, re-run with `teammate score --as-admin` and
GITHUB_TOKEN scoped to admin:repo.
```

## Output (Ollama down)

```
Local LLM (Ollama) not running — returning matching files instead of a
synthesized answer.

- compliance-vault/latest.md#chunk0 (score=2.105)
- compliance-vault/controls/k-isms-p/2.6.1.md#chunk0 (score=1.443)
...

Start Ollama (`ollama serve`) and re-run for a synthesized answer.
```

## Privacy

Everything happens locally. The query, the vault content, and the answer
never leave the user's laptop. No telemetry. No cloud round-trip.
