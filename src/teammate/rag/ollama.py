"""DEPRECATED: use ``teammate.providers.OllamaProvider``.

This module is a back-compat shim for v0.2 importers and will be removed in
v0.5. New code should import from ``teammate.providers`` directly.
"""

from __future__ import annotations

import warnings

from teammate.providers.ollama import (
    OllamaError,
    OllamaUnavailable,
)
from teammate.providers.ollama import (
    OllamaProvider as OllamaClient,
)

warnings.warn(
    "teammate.rag.ollama is deprecated; import from teammate.providers instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["OllamaClient", "OllamaError", "OllamaUnavailable"]
