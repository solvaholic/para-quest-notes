"""Prompt template loading and rendering.

stdlib ``string.Template`` for now (zero deps; PLAN.md leaves this open).
Each prompt exposes a stable hash (``prompt.id``) so the trace logger can
record exactly which template version produced a given LLM response.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from para_quest_notes.adapter.errors import ConfigError

PROMPT_SUFFIX = ".txt"


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str
    path: Path | None = None

    @property
    def id(self) -> str:
        """Stable, content-addressed identifier (sha256, 12 hex chars)."""
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        return f"{self.name}@{digest[:12]}"

    def render(self, **kwargs: Any) -> str:
        """Render with ``string.Template`` semantics (``$var`` / ``${var}``).

        Uses ``substitute`` (strict): missing keys raise. We want loud
        failure here - a silent missing variable in a prompt is exactly
        the kind of bug the eval harness can't catch.
        """
        return Template(self.text).substitute(**kwargs)


class PromptLoader:
    """Loads ``*.txt`` prompts from a directory."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)

    def get(self, name: str) -> Prompt:
        path = self.directory / f"{name}{PROMPT_SUFFIX}"
        if not path.is_file():
            raise ConfigError(f"prompt not found: {path}")
        return Prompt(name=name, text=path.read_text(encoding="utf-8"), path=path)

    def available(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted(p.stem for p in self.directory.glob(f"*{PROMPT_SUFFIX}"))
