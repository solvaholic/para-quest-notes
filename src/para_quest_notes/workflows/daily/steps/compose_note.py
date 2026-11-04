"""Step 6: compose_note (pure).

Build the final content for the destination:

* Parse with ``vault.frontmatter.split_note`` (tolerates legacy tail
  backmatter).
* Migrate any tail backmatter into frontmatter (frontmatter wins on
  conflict; tail fence dropped). Per-repo policy: every write-path
  workflow migrates backmatter on touch.
* Existing daily notes do **not** get canonical PARA frontmatter injected.
  ``docs/notes-system.md`` says daily notes inherit Quest context from
  their tasks and links, not from frontmatter. We preserve whatever
  frontmatter is there as-is (without forcing canonical key order),
  but we *do* drop the tail fence if the user had backmatter, and we
  migrate a legacy ``quest:`` classifier key to ``quest-kind:``.
* Missing daily notes select a whole-note template or the exact H1-only
  skeleton through the shared creation substrate. Template metadata is
  retained without generating daily PARA metadata.
* Prepend ``# YYYY-MM-DD\\n\\n`` to the body when the first non-blank
  line isn't already an ``# H1`` matching the filename's date.

No disk writes here — ``move_file`` handles those when ``--apply`` is set.
"""

from __future__ import annotations

import re

from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import (
    ParsedNote,
    canonical_frontmatter,
    dump_frontmatter,
    merge,
    migrate_quest_kind,
    split_note,
)
from para_quest_notes.workflows.creation import get_template_config, select_body

# Match the first non-blank line as an ATX H1, capturing its text.
_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$")


class ComposeNote:
    name = "compose_note"

    def __init__(self, *, template: str | None = None):
        self._template = template

    def run(self, ctx: StepContext) -> StepResult:
        date_iso: str = ctx.scratchpad["date_iso"]
        already: bool = ctx.scratchpad.get("already_at_destination", False)
        creating: bool = ctx.scratchpad.get("creating_missing", False)

        if creating:
            if ctx.vault is None:  # pragma: no cover - workflows always have a vault
                raise RuntimeError("daily workflow requires a vault")
            template_dir, _ = get_template_config(ctx.config.workflows if ctx.config else {})
            selected = select_body(
                template_name=self._template,
                skeleton=f"# {date_iso}\n\n",
                variables=_template_vars(date_iso),
                vault=ctx.vault,
                template_dir=template_dir,
            )
            body, ensured_h1 = _ensure_h1(selected.body, date_iso)
            h1_inserted = selected.body_source.startswith("skeleton") or ensured_h1
            frontmatter = canonical_frontmatter(selected.frontmatter)
            content = dump_frontmatter(frontmatter) + body
            ctx.scratchpad["content"] = content
            ctx.scratchpad["content_changed"] = True
            ctx.scratchpad["h1_inserted"] = h1_inserted
            ctx.scratchpad["frontmatter_migrated"] = selected.had_backmatter
            return StepResult(
                name=self.name,
                output={
                    "h1_inserted": h1_inserted,
                    "frontmatter_migrated": selected.had_backmatter,
                    "content_changed": True,
                    "body_source": selected.body_source,
                },
                meta={"creating_missing": True},
            )

        source = ctx.scratchpad["source_abs"]
        text = source.read_text(encoding="utf-8")
        split = split_note(text)

        # Migrate tail backmatter into frontmatter (frontmatter wins).
        if split.had_backmatter:
            merged_fm = merge(split.backmatter, split.frontmatter)
            frontmatter_migrated = True
        else:
            merged_fm = split.frontmatter
            frontmatter_migrated = False

        # Migrate a legacy ``quest:`` classifier to ``quest-kind:`` on touch,
        # even though daily otherwise preserves the user's frontmatter shape.
        merged_fm, quest_key_migrated = migrate_quest_kind(merged_fm)
        if quest_key_migrated:
            frontmatter_migrated = True

        body, h1_inserted = _ensure_h1(split.body, date_iso)

        # Render: preserve user frontmatter shape (no canonical reorder).
        if merged_fm:
            fm_text = ParsedNote(
                frontmatter=merged_fm,
                body="",
                had_frontmatter=True,
            ).render()
        else:
            fm_text = ""

        content = fm_text + body

        # Idempotent re-runs at the canonical path: only need to write
        # when content actually changed (H1 added or backmatter migrated).
        content_changed = (text != content) if already else True

        ctx.scratchpad["content"] = content
        ctx.scratchpad["content_changed"] = content_changed
        ctx.scratchpad["h1_inserted"] = h1_inserted
        ctx.scratchpad["frontmatter_migrated"] = frontmatter_migrated
        return StepResult(
            name=self.name,
            output={
                "h1_inserted": h1_inserted,
                "frontmatter_migrated": frontmatter_migrated,
                "content_changed": content_changed,
                "body_source": None,
            },
        )


def _template_vars(date_iso: str) -> dict[str, str]:
    year, month, day = date_iso.split("-")
    return {
        "title": date_iso,
        "date": date_iso,
        "created": date_iso,
        "year": year,
        "month": month,
        "day": day,
    }


def _ensure_h1(body: str, date_iso: str) -> tuple[str, bool]:
    """Prepend ``# YYYY-MM-DD\\n\\n`` to ``body`` unless an H1 already exists.

    "An H1 already exists" means: the first non-blank line is an ATX H1
    (``# ...``). We don't require the H1 text to *match* the date — if
    the user has a custom H1 like ``# Daily — May 12``, we leave it alone.
    """
    # Find the first non-blank line.
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _H1_RE.match(line):
            return body, False
        break  # first non-blank line is not an H1
    else:
        # body is empty or only blank lines.
        new = f"# {date_iso}\n"
        return new, True

    # Prepend the H1, leaving original body intact (one blank line gap).
    prefix = f"# {date_iso}\n\n"
    # Strip any leading blank lines from the body so we don't double-space.
    body_no_lead = body.lstrip("\n")
    return prefix + body_no_lead, True
