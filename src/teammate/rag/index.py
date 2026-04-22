"""Vault indexer — chunks markdown files, embeds via Ollama, stores in sqlite.

Index lives at ``.teammate-cache/vault.sqlite`` (per repo). Schema::

    chunks (
        id           INTEGER PRIMARY KEY,
        path         TEXT NOT NULL,           -- absolute path to source file
        chunk_idx    INTEGER NOT NULL,        -- 0-based chunk number within file
        text         TEXT NOT NULL,           -- the chunk text
        embedding    BLOB,                    -- pickled list[float], or NULL if no model
        token_count  INTEGER,                 -- approx; for budget tracking
        mtime        REAL NOT NULL,           -- source file mtime at index time
        framework    TEXT,                    -- parsed from frontmatter, optional
        control      TEXT,                    -- parsed from frontmatter, optional
        kind         TEXT                     -- score | evidence | advisory | attestation | doc
    )

    UNIQUE (path, chunk_idx)

Re-indexing is incremental: a file whose mtime hasn't changed since last
index is skipped. ``--rebuild`` flag in the CLI clears the table first.

Chunking strategy is intentionally simple: split on blank lines, then group
adjacent paragraphs into ~500-token windows. No semantic chunking, no
hierarchical embeddings. This is v0.1; smarter chunking is a v0.2 nice-to-have.
"""

from __future__ import annotations

import pickle
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from teammate.rag.ollama import OllamaClient, OllamaUnavailable

# ---------- chunking ----------

# A wildly approximate "tokens" estimator: 4 chars per token. Good enough
# to keep windows under the embedding model's input limit without pulling
# in tiktoken.
_CHARS_PER_TOKEN = 4
_TARGET_TOKENS_PER_CHUNK = 500
_TARGET_CHARS_PER_CHUNK = _TARGET_TOKENS_PER_CHUNK * _CHARS_PER_TOKEN


@dataclass(frozen=True, slots=True)
class Chunk:
    path: Path
    chunk_idx: int
    text: str
    framework: str
    control: str
    kind: str
    mtime: float


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and return (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    closing = text.find("\n---", 3)
    if closing == -1:
        return {}, text
    raw = text[3:closing].strip()
    body_start = text.find("\n", closing + 4)
    body = text[body_start + 1 :] if body_start != -1 else ""
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        meta = {}
    return meta if isinstance(meta, dict) else {}, body


def chunk_markdown(path: Path) -> list[Chunk]:
    """Read a markdown file, parse frontmatter, return Chunk list."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    meta, body = _parse_frontmatter(raw)
    framework = str(meta.get("framework", "")) if meta else ""
    control = str(meta.get("control", "")) if meta else ""
    kind = str(meta.get("teammate_kind", "doc")) if meta else "doc"
    mtime = path.stat().st_mtime if path.exists() else 0.0

    # Split on double newlines, group into target-size windows.
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_chars = 0
    chunk_idx = 0
    for para in paragraphs:
        if buf and buf_chars + len(para) > _TARGET_CHARS_PER_CHUNK:
            chunks.append(
                Chunk(
                    path=path,
                    chunk_idx=chunk_idx,
                    text="\n\n".join(buf),
                    framework=framework,
                    control=control,
                    kind=kind,
                    mtime=mtime,
                )
            )
            chunk_idx += 1
            buf = []
            buf_chars = 0
        buf.append(para)
        buf_chars += len(para) + 2
    if buf:
        chunks.append(
            Chunk(
                path=path,
                chunk_idx=chunk_idx,
                text="\n\n".join(buf),
                framework=framework,
                control=control,
                kind=kind,
                mtime=mtime,
            )
        )
    return chunks


# ---------- index db ----------


_SCHEMA = """\
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    chunk_idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB,
    token_count INTEGER,
    mtime REAL NOT NULL,
    framework TEXT,
    control TEXT,
    kind TEXT,
    UNIQUE (path, chunk_idx)
);

CREATE INDEX IF NOT EXISTS chunks_path_idx ON chunks(path);
CREATE INDEX IF NOT EXISTS chunks_kind_idx ON chunks(kind);
CREATE INDEX IF NOT EXISTS chunks_framework_idx ON chunks(framework);
"""


def open_index(cache_dir: Path) -> sqlite3.Connection:
    """Open or create the vault index db. Returns a connection."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "vault.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    return conn


def index_paths(
    paths: Iterable[Path],
    cache_dir: Path,
    ollama: OllamaClient | None = None,
    rebuild: bool = False,
) -> tuple[int, int]:
    """Index every markdown file in ``paths``. Returns (indexed, skipped).

    If ``ollama`` is provided and reachable, embed chunks. Otherwise leave
    embedding NULL — fallback retrieval will use keyword search.
    """
    conn = open_index(cache_dir)
    if rebuild:
        conn.execute("DELETE FROM chunks")
        conn.commit()

    indexed = 0
    skipped = 0

    new_chunks: list[Chunk] = []
    for path in paths:
        if not path.exists() or path.suffix != ".md":
            continue
        # Skip if already indexed at this mtime.
        cur = conn.execute(
            "SELECT MAX(mtime) FROM chunks WHERE path = ?", (str(path),)
        )
        last_mtime = cur.fetchone()[0]
        if last_mtime is not None and last_mtime >= path.stat().st_mtime - 1e-6:
            skipped += 1
            continue
        # File changed. Drop existing chunks for this path, re-chunk.
        conn.execute("DELETE FROM chunks WHERE path = ?", (str(path),))
        for chunk in chunk_markdown(path):
            new_chunks.append(chunk)
        indexed += 1

    if not new_chunks:
        conn.commit()
        conn.close()
        return indexed, skipped

    # Optionally embed in batches. Skip if Ollama is unavailable.
    embeddings: list[list[float] | None] = [None] * len(new_chunks)
    if ollama and ollama.is_up():
        try:
            batch_size = 32
            for i in range(0, len(new_chunks), batch_size):
                batch = new_chunks[i : i + batch_size]
                vecs = ollama.embed([c.text for c in batch])
                for j, vec in enumerate(vecs):
                    embeddings[i + j] = vec
        except OllamaUnavailable:
            pass  # leave embeddings as None; keyword search will handle it

    for chunk, vec in zip(new_chunks, embeddings, strict=False):
        blob = pickle.dumps(vec) if vec is not None else None
        token_estimate = max(1, len(chunk.text) // _CHARS_PER_TOKEN)
        conn.execute(
            "INSERT INTO chunks (path, chunk_idx, text, embedding, token_count, "
            "mtime, framework, control, kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(chunk.path),
                chunk.chunk_idx,
                chunk.text,
                blob,
                token_estimate,
                chunk.mtime,
                chunk.framework,
                chunk.control,
                chunk.kind,
            ),
        )
    conn.commit()
    conn.close()
    return indexed, skipped


def discover_indexable_files(roots: list[Path]) -> list[Path]:
    """Walk roots, return all .md files we should index.

    Currently indexes:
      - Everything under compliance-vault/ (the team's own state)
      - The root CLAUDE.md, if present (team's tribal knowledge)
      - docs/*.md (architecture/reference)
      - README.md (project context)
    """
    out: list[Path] = []
    for root in roots:
        root = root.resolve()
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".md":
            out.append(root)
            continue
        for relpath in (
            "compliance-vault",
            "docs",
        ):
            candidate = root / relpath
            if candidate.is_dir():
                out.extend(p for p in candidate.rglob("*.md"))
        for name in ("CLAUDE.md", "README.md"):
            p = root / name
            if p.exists():
                out.append(p)
    return sorted(set(out))


__all__ = [
    "Chunk",
    "chunk_markdown",
    "discover_indexable_files",
    "index_paths",
    "open_index",
]
