"""Vault — the Obsidian-format markdown nucleus.

Every scanner (score, watch, attest) writes here. The local-LLM layer
(``teammate ask`` and the MCP server) reads here. Built to be browsable
in Obsidian as-is — every file has YAML frontmatter, every link is a
plain markdown link, and the directory layout matches Obsidian's natural
folder grouping.

Layout::

    compliance-vault/
      .gitignore                  — `*` by default; teams opt-in to track
      latest.md                   — most recent score summary (overwritten)
      history/
        2026-04-26-1030.md        — append-only run records (timestamped)
      controls/
        iso-27001/
          A.5.2.md                — per-control evidence file
        k-isms-p/
          2.1.3.md
      advisories/
        2026-04-26-1030.md        — what watch.py noticed since last run
      attestations/
        2026-04-26-1030.pdf       — opt-in signed PDFs
        2026-04-26-1030.pdf.sig
        2026-04-26-1030.pdf.crt

Every markdown file carries YAML frontmatter::

    ---
    teammate_kind: score | advisory | attestation | evidence
    framework: iso-27001 | k-isms-p | "" (n/a)
    control: <id> | "" (n/a)
    score: <0..1> | null
    commit: <git-sha> | "" (no git)
    timestamp: 2026-04-26T10:30:00Z
    teammate_version: 0.1.0
    ---

Atomic write pattern: write to ``foo.md.tmp`` then rename to ``foo.md``.
On the same filesystem, rename is atomic (POSIX guarantee). If ``compliance-vault/``
crosses filesystems, set ``TEAMMATE_VAULT_NO_ATOMIC=1`` to skip the dance.
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from teammate import __version__

# ---------- public types ----------

VaultFrontmatter = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    """One probe's result, ready to be persisted as evidence."""

    probe_id: str
    result: str  # pass | partial | fail | n/a | indeterminate
    detail: str
    framework: str
    control_id: str
    severity: str = "medium"


@dataclass(frozen=True, slots=True)
class ScoreSummary:
    """Aggregated score across all probes for one run."""

    overall_pct: float | None  # passed/(passed+partial+failed); None if denominator is 0
    counts: dict[str, int]  # keys: pass, partial, fail, n_a, indeterminate
    timestamp: str  # ISO 8601 UTC
    commit: str  # git short SHA, "" if not a git repo
    target_path: str  # repo path that was scanned


# ---------- helpers ----------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(dt: datetime) -> str:
    """Filesystem-safe filename stamp: YYYY-MM-DD-HHMM."""
    return dt.strftime("%Y-%m-%d-%H%M")


def _iso(dt: datetime) -> str:
    """ISO 8601 with 'Z' suffix for UTC."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically (write tmp + rename).

    Set ``TEAMMATE_VAULT_NO_ATOMIC=1`` to bypass — only useful if the vault
    crosses filesystems (rare; usually only on weird container mounts).
    """
    if os.environ.get("TEAMMATE_VAULT_NO_ATOMIC"):
        path.write_text(content, encoding="utf-8")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _render_frontmatter(meta: VaultFrontmatter) -> str:
    """Render a YAML frontmatter block (between --- fences)."""
    body = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True).strip()
    return f"---\n{body}\n---\n"


def _slug_for_control(framework: str, control_id: str) -> str:
    """Filesystem-safe filename for a per-control evidence file."""
    safe = control_id.replace("/", "_")
    return f"controls/{framework}/{safe}.md"


# ---------- the Vault class ----------


class Vault:
    """Filesystem-backed vault.

    Designed to be safe to instantiate per-command. No long-lived state —
    everything reads/writes the underlying directory each call.

    ASCII-art of the write paths::

        ScoreSummary + [ProbeOutcome] ─► write_score_run() ─► latest.md
                                                          ├─► history/<stamp>.md
                                                          └─► controls/<framework>/<id>.md  (one per probe outcome)

        advisory_diff (dict)            ─► write_advisory_diff() ─► advisories/<stamp>.md
                                                                 └─► history/<stamp>.md (one-line summary entry)

        attestation_files (3 paths)     ─► write_attestation()    ─► attestations/<stamp>.pdf, .sig, .crt
                                                                 └─► history/<stamp>.md (one-line entry)
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    # ---- init / scaffolding ----

    def ensure_layout(self) -> None:
        """Create the vault directory tree if missing.

        Also drops a ``.gitignore`` containing ``*`` so the vault doesn't
        accidentally land in commits. Teams that DO want to track scoring
        history in git remove that gitignore explicitly.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in ("history", "advisories", "attestations", "controls"):
            (self.root / sub).mkdir(exist_ok=True)
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                textwrap.dedent(
                    """\
                    # Default: don't track the compliance vault in git.
                    # Vault contents may include partial paths, runtime hints,
                    # or evidence of internal state that's not appropriate to
                    # publish in a public repository.
                    #
                    # Teams who DO want their compliance history version-
                    # controlled (e.g. for SOC2 evidence) can remove this
                    # gitignore. teammate respects whatever you decide here.
                    *
                    """
                ),
                encoding="utf-8",
            )

    # ---- write paths ----

    def write_score_run(
        self,
        summary: ScoreSummary,
        outcomes: list[ProbeOutcome],
    ) -> Path:
        """Persist a score run. Returns the path of the timestamped history file."""
        self.ensure_layout()
        ts = _stamp(datetime.fromisoformat(summary.timestamp.replace("Z", "+00:00")))

        # 1. latest.md (overwritten each run)
        latest_md = self._render_summary_md(summary, outcomes, kind="latest")
        _atomic_write(self.root / "latest.md", latest_md)

        # 2. history/<ts>.md (append-only — one file per run)
        history_md = self._render_summary_md(summary, outcomes, kind="history")
        history_path = self.root / "history" / f"{ts}.md"
        _atomic_write(history_path, history_md)

        # 3. controls/<framework>/<id>.md (one per outcome — overwritten each run)
        for outcome in outcomes:
            if not outcome.framework or not outcome.control_id:
                continue  # probe with no control mapping — skip
            ctrl_path = self.root / _slug_for_control(outcome.framework, outcome.control_id)
            ctrl_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(ctrl_path, self._render_control_md(outcome, summary))

        return history_path

    def write_advisory_diff(
        self,
        source: str,
        new_items: list[dict[str, Any]],
        timestamp: str | None = None,
    ) -> Path:
        """Persist a watch-mode advisory diff. Returns the advisories/<ts>.md path."""
        self.ensure_layout()
        ts_dt = (
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if timestamp
            else _now_utc()
        )
        ts = _stamp(ts_dt)
        meta: VaultFrontmatter = {
            "teammate_kind": "advisory",
            "framework": "",
            "control": "",
            "score": None,
            "commit": "",
            "timestamp": _iso(ts_dt),
            "teammate_version": __version__,
            "source": source,
            "item_count": len(new_items),
        }

        body_lines = [
            f"# Advisory diff — {source}",
            "",
            f"_Captured at {_iso(ts_dt)} UTC. {len(new_items)} new item(s) since last run._",
            "",
        ]
        for item in new_items:
            title = str(item.get("title", "(no title)")).strip()
            link = str(item.get("link", "")).strip()
            published = str(item.get("published", "")).strip()
            body_lines.append(f"- **[{title}]({link})** — {published}")
            summary_text = str(item.get("summary", "")).strip()
            if summary_text:
                body_lines.append(f"  > {summary_text[:300]}")
        body_lines.append("")

        out = _render_frontmatter(meta) + "\n".join(body_lines)
        path = self.root / "advisories" / f"{ts}-{source}.md"
        _atomic_write(path, out)

        # Append a one-line history entry too — keeps `history/` chronological.
        # Filename includes source so two adjacent watch runs (KISA + NVD) within
        # the same minute don't collide.
        hist_meta = {**meta, "teammate_kind": "history-entry"}
        hist_body = (
            f"# Advisory diff — {source} ({len(new_items)} item(s))\n\n"
            f"See [advisories/{ts}-{source}.md](../advisories/{ts}-{source}.md) for details.\n"
        )
        _atomic_write(
            self.root / "history" / f"{ts}-advisory-{source}.md",
            _render_frontmatter(hist_meta) + hist_body,
        )
        return path

    def write_attestation(
        self,
        pdf_bytes: bytes,
        sig_bytes: bytes | None,
        crt_bytes: bytes | None,
        summary: ScoreSummary,
    ) -> Path:
        """Persist a PDF attestation (signed or unsigned). Returns the .pdf path."""
        self.ensure_layout()
        ts = _stamp(datetime.fromisoformat(summary.timestamp.replace("Z", "+00:00")))
        pdf_path = self.root / "attestations" / f"{ts}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        if sig_bytes:
            (self.root / "attestations" / f"{ts}.pdf.sig").write_bytes(sig_bytes)
        if crt_bytes:
            (self.root / "attestations" / f"{ts}.pdf.crt").write_bytes(crt_bytes)

        # Companion markdown describing the attestation in human-readable form.
        meta: VaultFrontmatter = {
            "teammate_kind": "attestation",
            "framework": "",
            "control": "",
            "score": summary.overall_pct,
            "commit": summary.commit,
            "timestamp": summary.timestamp,
            "teammate_version": __version__,
            "signed": bool(sig_bytes),
        }
        body = textwrap.dedent(
            f"""\
            # Attestation — {ts}

            - **Signed:** {"yes (sigstore keyless)" if sig_bytes else "no (preview only)"}
            - **Score:** {self._fmt_pct(summary.overall_pct)}
            - **Target commit:** `{summary.commit or "(no git)"}`
            - **Repo path:** `{summary.target_path}`

            PDF: [{ts}.pdf]({ts}.pdf)
            """
        )
        _atomic_write(
            self.root / "attestations" / f"{ts}.md",
            _render_frontmatter(meta) + body,
        )
        return pdf_path

    # ---- read paths (for RAG / MCP) ----

    def latest_summary_text(self) -> str | None:
        """Return latest.md text if it exists. Used by ask-vault and MCP."""
        p = self.root / "latest.md"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def iter_evidence(self, framework: str | None = None):
        """Yield (path, text) for every evidence markdown file.

        Used by the RAG indexer to embed all per-control evidence.
        """
        if framework:
            base = self.root / "controls" / framework
        else:
            base = self.root / "controls"
        if not base.exists():
            return
        for path in sorted(base.rglob("*.md")):
            yield path, path.read_text(encoding="utf-8")

    def iter_history(self):
        """Yield (path, text) for every historical run record."""
        base = self.root / "history"
        if not base.exists():
            return
        for path in sorted(base.glob("*.md")):
            yield path, path.read_text(encoding="utf-8")

    # ---- rendering ----

    def _render_summary_md(
        self, summary: ScoreSummary, outcomes: list[ProbeOutcome], kind: str
    ) -> str:
        meta: VaultFrontmatter = {
            "teammate_kind": "score" if kind == "history" else "score-latest",
            "framework": "",
            "control": "",
            "score": summary.overall_pct,
            "commit": summary.commit,
            "timestamp": summary.timestamp,
            "teammate_version": __version__,
            "counts": dict(summary.counts),
        }

        rows: list[str] = [
            "| Probe | Result | Framework / Control | Severity | Detail |",
            "|---|---|---|---|---|",
        ]
        for o in outcomes:
            ref = (
                f"{o.framework}:{o.control_id}"
                if o.framework and o.control_id
                else "(no control)"
            )
            detail = o.detail.replace("\n", " ").strip()
            if len(detail) > 80:
                detail = detail[:77] + "..."
            rows.append(f"| `{o.probe_id}` | {o.result} | {ref} | {o.severity} | {detail} |")

        body = textwrap.dedent(
            f"""\
            # teammate score — {summary.timestamp}

            **Overall:** {self._fmt_pct(summary.overall_pct)}
            **Target:** `{summary.target_path}`
            **Commit:** `{summary.commit or "(no git)"}`

            **Counts:** pass={summary.counts.get("pass", 0)} · partial={summary.counts.get("partial", 0)} · fail={summary.counts.get("fail", 0)} · n/a={summary.counts.get("n_a", 0)} · indeterminate={summary.counts.get("indeterminate", 0)}

            ## Probes

            """
        ) + "\n".join(rows) + "\n"

        return _render_frontmatter(meta) + body

    def _render_control_md(self, outcome: ProbeOutcome, summary: ScoreSummary) -> str:
        meta: VaultFrontmatter = {
            "teammate_kind": "evidence",
            "framework": outcome.framework,
            "control": outcome.control_id,
            "score": None,
            "commit": summary.commit,
            "timestamp": summary.timestamp,
            "teammate_version": __version__,
            "result": outcome.result,
            "severity": outcome.severity,
            "probe": outcome.probe_id,
        }
        body = textwrap.dedent(
            f"""\
            # {outcome.framework}:{outcome.control_id}

            - **Probe:** `{outcome.probe_id}`
            - **Result:** **{outcome.result}**
            - **Severity:** {outcome.severity}
            - **Captured at:** {summary.timestamp}
            - **Target commit:** `{summary.commit or "(no git)"}`

            ## Evidence

            {outcome.detail}
            """
        )
        return _render_frontmatter(meta) + body

    @staticmethod
    def _fmt_pct(pct: float | None) -> str:
        if pct is None:
            return "n/a (no scorable probes ran)"
        return f"{pct * 100:.1f}%"


__all__ = [
    "ProbeOutcome",
    "ScoreSummary",
    "Vault",
]
