"""Minimal Ollama HTTP client.

Ollama exposes ``POST /api/embed`` (newer API) / ``POST /api/embeddings`` (older)
and ``POST /api/generate`` for completion + ``POST /api/chat`` for chat. We only
need:

  - ``embed(texts, model)`` - return list[list[float]]
  - ``generate(prompt, model, system=...)`` - return generator[str]

We hit raw HTTP via ``httpx`` rather than the official Ollama Python client
because we want the dependency footprint minimal and we don't need streaming
chat history. ``httpx`` is already in the optional ``rag`` extras.

If Ollama isn't running, every call raises ``OllamaUnavailable``. Callers
should catch and degrade gracefully (fall back to keyword search, etc).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from teammate.rag import DEFAULT_EMBEDDING_MODEL, DEFAULT_LLM_MODEL, DEFAULT_OLLAMA_HOST


class OllamaUnavailable(RuntimeError):
    """Ollama is not reachable. Caller should fall back gracefully."""


class OllamaError(RuntimeError):
    """Ollama responded but errored. Usually a missing model."""


class OllamaClient:
    """Lightweight Ollama HTTP wrapper.

    ``timeout_s`` applies per request. Embedding requests are short
    (sub-second on a small model). Generate requests stream — the timeout
    governs the time-to-first-token, not the full response.
    """

    def __init__(
        self,
        host: str | None = None,
        llm_model: str | None = None,
        embedding_model: str | None = None,
        timeout_s: float = 30.0,
    ):
        self.host = (host or DEFAULT_OLLAMA_HOST).rstrip("/")
        self.llm_model = llm_model or DEFAULT_LLM_MODEL
        self.embedding_model = embedding_model or DEFAULT_EMBEDDING_MODEL
        self.timeout_s = timeout_s

    # ---- health ----

    def is_up(self) -> bool:
        """Quick health check. Returns False if Ollama isn't running."""
        try:
            import httpx
        except ImportError:
            return False
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=2.0)
            return r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            return False

    def list_models(self) -> list[str]:
        """Return names of locally-pulled models."""
        try:
            import httpx
        except ImportError as exc:
            raise OllamaUnavailable("httpx not installed") from exc
        try:
            r = httpx.get(f"{self.host}/api/tags", timeout=self.timeout_s)
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise OllamaUnavailable(str(exc)) from exc
        r.raise_for_status()
        data = r.json()
        return [m["name"] for m in data.get("models", [])]

    # ---- embeddings ----

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Embed a batch of texts. Returns one vector per input.

        Tries the newer ``/api/embed`` endpoint first; falls back to
        ``/api/embeddings`` (singular) for older Ollama versions.
        """
        try:
            import httpx
        except ImportError as exc:
            raise OllamaUnavailable("httpx not installed") from exc

        m = model or self.embedding_model
        # Newer batch endpoint:
        payload: dict[str, Any] = {"model": m, "input": texts}
        try:
            r = httpx.post(
                f"{self.host}/api/embed", json=payload, timeout=self.timeout_s
            )
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise OllamaUnavailable(str(exc)) from exc

        if r.status_code == 200:
            return r.json()["embeddings"]
        if r.status_code == 404:
            # Older Ollama — fall back to singular endpoint, one at a time.
            out: list[list[float]] = []
            for t in texts:
                try:
                    rr = httpx.post(
                        f"{self.host}/api/embeddings",
                        json={"model": m, "prompt": t},
                        timeout=self.timeout_s,
                    )
                    rr.raise_for_status()
                    out.append(rr.json()["embedding"])
                except (httpx.HTTPError, OSError) as exc:
                    raise OllamaError(f"embedding failed: {exc}") from exc
            return out
        raise OllamaError(f"embed failed: HTTP {r.status_code}: {r.text[:200]}")

    # ---- generation ----

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        stream: bool = True,
    ) -> Iterator[str]:
        """Stream tokens from Ollama. Yields chunks of generated text.

        If ``stream=False``, yields the full response as one string.
        """
        try:
            import httpx
        except ImportError as exc:
            raise OllamaUnavailable("httpx not installed") from exc

        m = model or self.llm_model
        payload: dict[str, Any] = {
            "model": m,
            "prompt": prompt,
            "stream": stream,
        }
        if system:
            payload["system"] = system

        try:
            with httpx.stream(
                "POST",
                f"{self.host}/api/generate",
                json=payload,
                timeout=self.timeout_s,
            ) as r:
                if r.status_code != 200:
                    body = r.read().decode("utf-8", errors="ignore")[:200]
                    raise OllamaError(f"generate failed: HTTP {r.status_code}: {body}")
                if not stream:
                    body = r.read().decode("utf-8", errors="ignore")
                    try:
                        data = json.loads(body)
                        yield data.get("response", "")
                        return
                    except json.JSONDecodeError as exc:
                        raise OllamaError(f"non-streaming parse failed: {exc}") from exc
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "response" in chunk:
                        yield chunk["response"]
                    if chunk.get("done"):
                        break
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise OllamaUnavailable(str(exc)) from exc


__all__ = ["OllamaClient", "OllamaError", "OllamaUnavailable"]
