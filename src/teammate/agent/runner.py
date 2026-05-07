"""Stub dispatcher for colleague-agent routines.

Real-world deployment: the Anthropic-cloud ``/schedule`` runner (or a
self-hosted GitHub Actions cron) reads a routines config like
``examples/agent-routines.json``, picks a routine name, and calls
:func:`run_routine`. It then takes the resulting artifact files and
distributes them — Slack messages, GitHub issues, PR comments —
using whatever scoped tokens the runner holds.

The agent itself does *none* of the distribution. That's why this
module is intentionally tiny: dispatch + return.
"""

from __future__ import annotations

from collections.abc import Callable

from teammate.agent.base import RoutineConfig, RoutineResult
from teammate.agent.orphan_triage import run as _orphan_triage_run
from teammate.agent.pr_migration_plan import run as _pr_migration_plan_run
from teammate.agent.weekly_digest import run as _weekly_digest_run

_REGISTRY: dict[str, Callable[[RoutineConfig], RoutineResult]] = {
    "weekly_digest": _weekly_digest_run,
    "orphan_triage": _orphan_triage_run,
    "pr_migration_plan": _pr_migration_plan_run,
}


def list_routines() -> list[str]:
    """Stable order — what `agent run` shows in --help."""
    return sorted(_REGISTRY.keys())


def run_routine(name: str, config: RoutineConfig) -> RoutineResult:
    """Dispatch to the named routine. Raises ``KeyError`` on unknown names."""
    if name not in _REGISTRY:
        raise KeyError(
            f"unknown routine: {name!r}. Known: {', '.join(list_routines())}"
        )
    return _REGISTRY[name](config)


__all__ = ["list_routines", "run_routine"]
