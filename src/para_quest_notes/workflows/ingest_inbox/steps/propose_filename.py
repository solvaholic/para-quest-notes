"""Step 4: propose_filename (LLM, with auto-skip for good source names).

Two-tier behavior:

1. If the inbox source basename already passes a strict structural check
   (Title Case with spaces between words), keep it as-is and skip the
   LLM entirely. This preserves user-curated filenames (dates,
   specificity, brand names like ``DeepWiki``) that the LLM would
   otherwise rewrite-and-lose.
2. Otherwise, call the LLM with a bounded-choice prompt: pick ``keep``,
   ``repair`` (mechanical first-letter capitalization), or ``generate``
   (judgment from title + body). The returned filename is validated
   against the same structural check; failure escalates.

The collision check (via :mod:`para_quest_notes.workflows.validate`)
runs in both branches.
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
BODY_PREVIEW_CHARS = 2000


def _passes_structural_check(stem: str) -> bool:
    """Strict structural check for filename stems.

    A stem passes when:
    - the full ``<stem>.md`` matches :data:`_FILENAME_OK` (allowed chars,
      no path separators or underscores), and
    - every whitespace-separated word's first *alphanumeric* character is
      an uppercase letter or a digit (strict — no lowercase joiners like
      ``a``, ``of``, ``to``; brand names with interior caps like
      ``DeepWiki`` are fine). Leading punctuation is skipped, so words
      like ``(Python`` pass and pure-punctuation words like the ``-`` in
      ``Sheet - Python`` are allowed.
    """
    if not _FILENAME_OK.match(f"{stem}.md"):
        return False
    words = stem.split()
    if not words:
        return False
    for w in words:
        first_alnum = next((c for c in w if c.isalnum()), None)
        if first_alnum is None:
            continue  # pure-punctuation word, e.g. the "-" in "A - B"
        if not (first_alnum.isupper() or first_alnum.isdigit()):
            return False
    return True


def _mechanical_repair(stem: str) -> str:
    """Deterministic first-letter capitalization of each whitespace word.

    Collapses runs of whitespace. Does *not* split snake_case / camelCase
    / kebab-case tokens — those are judgment calls and belong in the
    LLM's ``generate`` branch.
    """
    words = stem.split()
    fixed: list[str] = []
    for w in words:
        if w and w[0].isalpha():
            fixed.append(w[0].upper() + w[1:])
        else:
            fixed.append(w)
    return " ".join(fixed)


class ProposeFilename:
    name = "propose_filename"

    def __init__(self, prompt: Prompt, *, model: str | None = None):
        self.prompt = prompt
        self.model = model

    def run(self, ctx: StepContext) -> StepResult:
        scan: ScanResult = ctx.scratchpad["scan"]
        vault: Path = ctx.vault if ctx.vault is not None else scan.source.parent.parent
        para_type = ctx.scratchpad.get("para_type") or "unknown"

        source_stem = scan.source.stem
        source_basename = scan.source.name

        if _passes_structural_check(source_stem):
            filename = source_basename
            reason = "source filename already passes the structural check"
            choice = "keep"
            return self._finalize(
                ctx,
                vault,
                scan.source,
                filename,
                reason=reason,
                choice=choice,
                used_llm=False,
            )

        repaired_stem = _mechanical_repair(source_stem)
        repaired = f"{repaired_stem}.md"

        parsed = call_llm_json(
            ctx_llm=ctx.llm,
            prompt=self.prompt,
            render_vars={
                "title": scan.title,
                "body": scan.parsed.body.strip()[:BODY_PREVIEW_CHARS] or "(empty)",
                "para_type": para_type,
                "source_basename": source_basename,
                "repaired_basename": repaired,
            },
            step_name=self.name,
            model=self.model,
        )
        filename = str(require(parsed, "filename", step=self.name, expected="string")).strip()
        choice = str(parsed.get("choice", "")).strip().lower() or "generate"
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
                context={"filename": filename, "choice": choice},
            )
        if not _passes_structural_check(filename[:-3]):
            raise EscalateToUser(
                step=self.name,
                reason="filename is not Title Case; each word must start with an "
                "uppercase letter or digit",
                options=[],
                context={"filename": filename, "choice": choice},
            )

        return self._finalize(
            ctx,
            vault,
            scan.source,
            filename,
            reason=reason,
            choice=choice,
            used_llm=True,
        )

    def _finalize(
        self,
        ctx: StepContext,
        vault: Path,
        source: Path,
        filename: str,
        *,
        reason: str,
        choice: str,
        used_llm: bool,
    ) -> StepResult:
        collision_issues = check_basename_available(vault, filename, ignore_path=source)
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
            meta={"filename": filename, "choice": choice, "used_llm": used_llm},
        )
