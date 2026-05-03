# Choosing the Stack — When to Pick teammate (and When Not To)

teammate is built on one thesis: a team's brain belongs in the team's git repo, queried by a local LLM, indexed once per laptop. If federation, audit trail, and sovereignty are not all three required, a simpler tool is the better answer.

## Decision rule

This table is the canonical decision rule. It is reproduced verbatim from the [stack comparison matrix](https://github.com/JIUNG9/teammate) used across all teammate documentation.

| Situation | Pick |
|---|---|
| Solo notebook, beautiful graph view | Obsidian |
| Solo + AI managing your knowledge graph | gbrain |
| Team + vendor-trusting + non-regulated industry | Cloud RAG |
| **Team + audit + sovereignty + AI** | **teammate (git + sqlite-vec + Ollama)** |

## Solo notebook, beautiful graph view → Obsidian

Pick Obsidian when the brain has exactly one author and the graph view is the point. Obsidian's UX, plugin ecosystem, and offline-first model are best-in-class for personal knowledge. teammate gives up the GUI, the canvas, and the rich plugin surface in this scenario. teammate is the wrong choice for a solo user who just wants pretty backlinks — there is no team to federate with, no PR review to gain, and the CLI overhead is not earned.

## Solo + AI managing your knowledge graph → gbrain

Pick gbrain when one person wants an AI-curated exocortex with a first-class local AI graph layer. gbrain's strength is single-user AI ingest and timeline tracking on a local Postgres. teammate gives up the AI-managed graph, the per-user ingest pipeline, and the timeline UX. teammate is the wrong choice when there is no team — the federation layer (`git push` / `git pull`) is the whole reason the architecture exists, and a single-user repo doesn't exercise it.

## Team + vendor-trusting + non-regulated industry → Cloud RAG (Notion / Confluence / Teamspace)

Pick Cloud RAG when the team is comfortable with vendor-managed infrastructure and the data is not regulated, sensitive, or under exfil constraints. Notion AI, Confluence AI, and similar products give you SSO, real-time co-edit, and zero local setup. teammate gives up real-time co-edit, the polished web UI, and SSO out of the box. teammate is the wrong choice when the team values frictionless onboarding over data sovereignty and has no compliance pressure pushing them off the cloud.

## Team + audit + sovereignty + AI → teammate

Pick teammate when all three constraints are required: more than one engineer (federation), code-review for docs (`git log` / `git blame` audit trail), and data that cannot leave your infrastructure (local LLM, local index). teammate gives up the GUI, real-time co-edit, and per-engineer indexing time (~10 seconds on first init). teammate is the wrong choice when any of those three constraints is optional — a simpler tool wins.

## If you picked teammate

Install and bootstrap in five minutes — see [QUICKSTART.md](QUICKSTART.md). Source and issue tracker: [github.com/JIUNG9/teammate](https://github.com/JIUNG9/teammate).
