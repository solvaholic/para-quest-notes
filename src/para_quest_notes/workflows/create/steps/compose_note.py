"""Step 4: compose_note (pure).

Composes the final note content: canonical frontmatter (via
``vault.frontmatter.dump_frontmatter`` — single source of truth) plus a
type-appropriate body skeleton.

Body skeletons are intentionally bare: a one-line purpose placeholder,
the canonical sections for the type, and an empty ``Notes`` block. The
user fills them in.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import dump_frontmatter
from para_quest_notes.workflows.create.contract import CreateInputs

_PROJECT_BODY = """# {title}

<one-sentence purpose>

## Goals

- <what does done look like?>

## Approach

<initial sketch; OK to leave a placeholder>

## Tasks

- [ ] <first concrete next step>

## Notes

<dated entries as the work happens>
"""

_AREA_BODY = """# {title}

<one-sentence purpose>

## What This Is

<scope; what belongs in this area>

## Notes

<ongoing thinking>
"""

_RESOURCE_BODY = """# {title}

<one-sentence summary>

## Source

{source_block}

## Notes

<takeaways, quotes, why this matters>
"""


def _body_for(inputs: CreateInputs, title: str) -> str:
    if inputs.type == "project":
        return _PROJECT_BODY.format(title=title)
    if inputs.type == "area":
        return _AREA_BODY.format(title=title)
    source_block = inputs.source_url or "<URL, attribution, retrieved date>"
    return _RESOURCE_BODY.format(title=title, source_block=source_block)


def _frontmatter_for(inputs: CreateInputs, *, today: str) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "type": inputs.type,
        "quest": inputs.quest,
        "supports": list(inputs.supports) if inputs.supports else None,
        "source_url": inputs.source_url,
        "created": today,
    }
    return fm


class ComposeNote:
    name = "compose_note"

    def __init__(self, *, today: str | None = None):
        # Injectable for deterministic tests.
        self._today = today

    def run(self, ctx: StepContext) -> StepResult:
        inputs: CreateInputs = ctx.scratchpad["inputs"]
        title: str = ctx.scratchpad["title"]
        today = self._today or date.today().isoformat()

        fm = _frontmatter_for(inputs, today=today)
        fm_text = dump_frontmatter(fm)
        body = _body_for(inputs, title)
        content = fm_text + body

        ctx.scratchpad["content"] = content
        ctx.scratchpad["frontmatter"] = fm
        return StepResult(
            name=self.name,
            output={"frontmatter": fm, "bytes": len(content.encode("utf-8"))},
        )
