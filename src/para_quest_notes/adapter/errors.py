"""Adapter exception hierarchy.

``EscalateToUser`` is the workflow-control exception: a step raises it when
no rule fits and the user needs to decide. The workflow runner catches it,
records the structured payload, and stops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class AdapterError(Exception):
    """Base class for adapter errors."""


class ConfigError(AdapterError):
    """Raised when tool config is missing required values or malformed."""


class VaultError(AdapterError):
    """Raised when no vault can be resolved."""


class LLMError(AdapterError):
    """Raised when an LLM call fails after retries or returns unparseable output."""


@dataclass
class EscalateToUser(Exception):
    """Workflow-control exception: stop and ask the user.

    ``options`` is a list of structured choices the workflow can offer; use
    free-form ``reason`` for everything else. Workflows should keep this
    payload serializable - it's the contract the CLI surfaces as JSON.
    """

    step: str
    reason: str
    options: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"escalate({self.step}): {self.reason}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "reason": self.reason,
            "options": self.options,
            "context": self.context,
        }
