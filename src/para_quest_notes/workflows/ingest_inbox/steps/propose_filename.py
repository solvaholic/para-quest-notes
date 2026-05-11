"""Step 4: propose_filename (LLM).

LLM proposes a Title Case filename. We validate it locally (no slashes,
.md suffix, non-empty), then ask :mod:`para_quest_notes.workflows.validate`
whether the basename would collide with an existing note. On collision
the step escalates with candidate alternatives.
"""

from __future__ import annotations

import re
from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import Prompt
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.ingest_inbox.steps._llm import call_llm_json, require
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanResult
from para_quest_notes.workflows.validate.api import check_basename_available

# Allowed characters: letters, digits, spaces, and a small punctuation set.
# Notably no underscore (rejects snake_case stems).
_FILENAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-()'.,&]*\.md$")
# A lowercase letter immediately followed by an uppercase letter is the
# tell of camelCase / PascalCase. Title Case puts a space between words.
_INTERIOR_CAPS = re.compile(r"[a-z][A-Z]")
BODY_PREVIEW_CHARS = 2000


def _looks_like_title_case(stem: str) -> bool:
    """Reject obvious camelCase / PascalCase stems.

    We don't try to enforce *every* Title Case rule (articles, prepositions,
    etc.) — just the structural one that catches the common LLM failure
    mode: jamming the title into one CapWord.
    """
    return _INTERIOR_CAPS.search(stem) is None


class ProposeFilename:
    name = "propose_filename"

    def __init__(self, prompt: Prompt, *, model: str | None = None):
        self.prompt = prompt
        self.model = model

    def run(self, ctx: StepContext) -> StepResult:
        scan: ScanResult = ctx.scratchpad["scan"]
        vault: Path = ctx.vault if ctx.vault is not None else scan.source.parent.parent
        para_type = ctx.scratchpad.get("para_type") or "unknown"

        parsed = call_llm_json(
            ctx_llm=ctx.llm,
            prompt=self.prompt,
            render_vars={
                "title": scan.title,
                "body": scan.parsed.body.strip()[:BODY_PREVIEW_CHARS] or "(empty)",
                "para_type": para_type,
            },
            step_name=self.name,
            model=self.model,
        )
        filename = str(require(parsed, "filename", step=self.name, expected="string")).strip()
        reason = str(parsed.get("reason", ""))

        if "/" in filename or "\\" in filename:
            raise EscalateToUser(
                step=self.name,
                reason="filename must not contain path separators",
                options=[],
                context={"filename": filename},
            )
        if not filename.endswith(".md"):
            filename = f"{filename}.md"
        if not _FILENAME_OK.match(filename):
            raise EscalateToUser(
                step=self.name,
                reason="filename has disallowed characters",
                options=[],
                context={"filename": filename},
            )
        if not _looks_like_title_case(filename[:-3]):
            raise EscalateToUser(
                step=self.name,
                reason="filename looks like camelCase or PascalCase; use Title Case "
                "(words separated by spaces)",
                options=[],
                context={"filename": filename},
            )

        collision_issues = check_basename_available(vault, filename, ignore_path=scan.source)
        if collision_issues:
            issue = collision_issues[0]
            existing = [{"filename": filename, "existing": rel} for rel in issue.related]
            raise EscalateToUser(
                step=self.name,
                reason="filename collides with existing note(s)",
                options=existing,
                context={"reason": reason, "validate_message": issue.message},
            )

        ctx.scratchpad["filename"] = filename
        return StepResult(
            name=self.name,
            output={"filename": filename, "reason": reason},
            meta={"filename": filename},
        )
