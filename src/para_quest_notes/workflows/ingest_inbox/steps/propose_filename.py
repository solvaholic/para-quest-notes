"""Step 4: propose_filename (LLM).

LLM proposes a Title Case filename. We validate it locally (no slashes,
.md suffix, non-empty), then check for collisions across the vault
excluding ``archive/``. On collision the step escalates with
candidate alternatives.
"""

from __future__ import annotations

import re
from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import Prompt
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.ingest_inbox.steps._llm import call_llm_json, require
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanResult

# Conservative validator: word chars, spaces, hyphens, parens, apostrophes.
_FILENAME_OK = re.compile(r"^[\w][\w \-()'.,&]*\.md$")
BODY_PREVIEW_CHARS = 2000


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

        collisions = _find_collisions(vault, filename, ignore=scan.source)
        if collisions:
            raise EscalateToUser(
                step=self.name,
                reason="filename collides with existing note(s)",
                options=[
                    {"filename": filename, "existing": str(p.relative_to(vault).as_posix())}
                    for p in collisions
                ],
                context={"reason": reason},
            )

        ctx.scratchpad["filename"] = filename
        return StepResult(
            name=self.name,
            output={"filename": filename, "reason": reason},
            meta={"filename": filename},
        )


def _find_collisions(vault: Path, filename: str, *, ignore: Path) -> list[Path]:
    target_lower = filename.lower()
    matches: list[Path] = []
    for md in vault.rglob("*.md"):
        try:
            rel = md.relative_to(vault)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == "archive":
            continue
        if md.resolve() == ignore.resolve():
            continue
        if md.name.lower() == target_lower:
            matches.append(md)
    return matches
