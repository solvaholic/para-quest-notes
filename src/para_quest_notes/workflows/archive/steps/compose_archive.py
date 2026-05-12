"""Step 6: compose_archive (pure).

Builds the archived note's final content and the archive destination
path. No disk writes here — write_and_move handles those when
``--apply`` is set.

Rules:

* **Frontmatter is canonical.** ``vault.frontmatter.canonical_frontmatter``
  orders keys and drops empty/None. Legacy backmatter (if any) is
  merged into frontmatter (frontmatter wins on conflict), then the
  backmatter fence is removed from the body.
* **Open tasks** in the canonical candidate set (from
  scan_open_tasks) are rewritten ``[ ]``/``[/]`` -> ``[-]`` with a
  ``❌ <today>`` cancellation marker. Block-id-aware: when a line
  ends with ``^abc123``, the marker goes *before* the block id so
  the reference stays at end-of-line. Skips lines that already carry
  Obsidian Tasks emoji metadata (📅 ⏳ 🛫 🔁) — surface those rather
  than blindly appending.
* **``## Outcome``** is appended at the end of the body when
  ``outcome_action == "inserted"``. When ``kept``, body is unchanged.
* **Destination** mirrors the source's sub-path under ``archive/``:
  ``projects/foo/X.md`` -> ``archive/projects/foo/X.md``.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import (
    canonical_frontmatter,
    dump_frontmatter,
    merge,
)

# Obsidian Tasks emoji metadata that lives on a task line. Presence of
# any of these means the line has scheduling/recurrence/due info we
# shouldn't silently bulldoze.
_TASKS_META_EMOJI = ("📅", "⏳", "🛫", "🔁", "✅", "❌")
_BLOCK_ID = re.compile(r"\s+\^[A-Za-z0-9-]+\s*$")


class ComposeArchive:
    name = "compose_archive"

    def __init__(self, *, today: str | None = None):
        # Injectable for deterministic tests.
        self._today = today

    def run(self, ctx: StepContext) -> StepResult:
        split = ctx.scratchpad["split"]
        vault: Path = ctx.vault  # type: ignore[assignment]
        source_rel: str = ctx.scratchpad["source_rel"]
        open_tasks: list[dict[str, Any]] = ctx.scratchpad.get("open_tasks", [])
        will_cancel: bool = ctx.scratchpad.get("will_cancel_tasks", False)
        outcome_action: str = ctx.scratchpad["outcome_action"]
        outcome_text: str | None = ctx.scratchpad.get("outcome_text")
        today = self._today or date.today().isoformat()

        # 1. Merge front + back into a single canonical frontmatter dict.
        combined = merge(split.backmatter, split.frontmatter)
        new_fm = canonical_frontmatter(combined)
        frontmatter_migrated = split.had_backmatter

        # 2. Rewrite cancelled tasks in body.
        body = split.body
        tasks_cancelled = 0
        skipped_meta: list[int] = []
        if will_cancel and open_tasks:
            new_body, tasks_cancelled, skipped_meta = _rewrite_open_tasks(
                body, open_tasks, today=today
            )
            body = new_body
            if skipped_meta:
                raise EscalateToUser(
                    step=self.name,
                    reason=(
                        "some open tasks carry Obsidian Tasks scheduling "
                        "metadata (📅/⏳/🛫/🔁); resolve them in the editor "
                        "and re-run"
                    ),
                    options=[{"line": ln} for ln in skipped_meta],
                    context={"source": source_rel},
                )

        # 3. Append ## Outcome if inserted.
        if outcome_action == "inserted" and outcome_text:
            body = _append_outcome(body, outcome_text)

        # 4. Render the new note: canonical frontmatter + body. We drop
        #    any deprecated tail backmatter and preserve the body's
        #    trailing whitespace shape.
        fm_text = dump_frontmatter(new_fm)
        body_with_trailing = body
        if split.had_backmatter:
            body_with_trailing = body.rstrip("\n") + "\n"
        content = fm_text + body_with_trailing

        # 5. Compute archive destination (mirror sub-path under archive/).
        rel = Path(source_rel)  # e.g. projects/foo/X.md
        dest_rel = Path("archive") / rel
        dest_abs = vault / dest_rel
        dest_rel_posix = dest_rel.as_posix()

        ctx.scratchpad["content"] = content
        ctx.scratchpad["destination_abs"] = dest_abs
        ctx.scratchpad["destination_rel"] = dest_rel_posix
        ctx.scratchpad["tasks_cancelled"] = tasks_cancelled
        ctx.scratchpad["frontmatter_migrated"] = frontmatter_migrated
        return StepResult(
            name=self.name,
            output={
                "destination": dest_rel_posix,
                "tasks_cancelled": tasks_cancelled,
                "outcome_action": outcome_action,
                "frontmatter_migrated": frontmatter_migrated,
            },
            meta={"destination": dest_rel_posix},
        )


def _rewrite_open_tasks(
    body: str,
    tasks: list[dict[str, Any]],
    *,
    today: str,
) -> tuple[str, int, list[int]]:
    """Rewrite the lines named in ``tasks`` from ``[ ]``/``[/]`` -> ``[-]``.

    Returns ``(new_body, n_cancelled, skipped_line_numbers)``. A task is
    skipped (and its line number added to the skipped list) when its
    text already carries Obsidian Tasks emoji metadata. We DO append
    the cancellation marker block-id-aware: marker goes before the
    block id.
    """
    by_line = {int(t["line"]): t for t in tasks}
    out_lines: list[str] = []
    cancelled = 0
    skipped: list[int] = []
    for idx, line in enumerate(body.splitlines(keepends=False), start=1):
        if idx not in by_line:
            out_lines.append(line)
            continue
        t = by_line[idx]
        text = str(t["text"])
        bullet = str(t["bullet"])
        if any(em in text for em in _TASKS_META_EMOJI):
            skipped.append(idx)
            out_lines.append(line)
            continue

        marker = f"❌ {today}"
        block_match = _BLOCK_ID.search(text)
        if block_match is not None:
            head = text[: block_match.start()].rstrip()
            block = block_match.group(0).strip()
            new_text = f"{head} {marker} {block}"
        else:
            new_text = f"{text.rstrip()} {marker}"
        out_lines.append(f"{bullet}[-] {new_text}")
        cancelled += 1

    # Preserve trailing newline if the original had one.
    trailer = "\n" if body.endswith("\n") else ""
    return ("\n".join(out_lines) + trailer, cancelled, skipped)


def _append_outcome(body: str, outcome_text: str) -> str:
    """Append a fresh ``## Outcome`` section to the end of the body."""
    text = outcome_text.strip()
    block = f"## Outcome\n\n{text}\n"
    if not body:
        return block
    # Ensure exactly one blank line between the previous content and
    # the new section.
    stripped = body.rstrip("\n")
    return f"{stripped}\n\n{block}"
