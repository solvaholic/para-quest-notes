"""Step 5: compose_note (pure).

Composes the final note content: canonical frontmatter (via
``vault.frontmatter.dump_frontmatter`` - single source of truth) plus a
body from one of three sources (in priority order):

1. **stdin body** (``inputs.body``) - piped content replaces everything
   and uses the same variable substitution as template bodies
2. **template** (``inputs.template`` or config default) - loaded from
   ``<vault>/resources/templates/<name>.md`` and variable-substituted
3. **built-in skeleton** - type-appropriate minimal structure

A selected template may include frontmatter. Template metadata merges beneath
generated metadata, while its body keeps the existing variable-substitution
behavior. Legacy template backmatter is tolerated and migrated through the
shared vault frontmatter helpers.

Body skeletons are intentionally bare: a one-line purpose placeholder,
the canonical sections for the type, and an empty ``Notes`` block. The
user fills them in.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import (
    canonical_frontmatter,
    dump_frontmatter,
    merge,
    split_note,
)
from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.templates import (
    TemplateNotFoundError,
    build_template_variables,
    get_template_config,
    load_template,
    render_template,
    select_template_name,
)

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
        "quest-kind": inputs.quest,
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

        template_frontmatter: dict[str, Any] = {}

        variables = build_template_variables(inputs, title=title, today=today)

        # Explicit merge > ordinary stdin > template > built-in skeleton.
        body: str
        body_source = "skeleton"
        if "merged_template_body" in ctx.scratchpad:
            body = ctx.scratchpad["merged_template_body"]
            template_frontmatter = dict(ctx.scratchpad["merged_template_frontmatter"])
            body_source = f"merged-template:{ctx.scratchpad['merged_template_name']}"
        elif inputs.body is not None:
            body = render_template(inputs.body, variables)
            body_source = "stdin"
        elif ctx.vault is not None and (template_name := self._resolve_template_name(inputs, ctx)):
            template_dir, _ = get_template_config(ctx.config.workflows if ctx.config else {})
            try:
                raw = load_template(template_name, vault=ctx.vault, template_dir=template_dir)
                split = split_note(raw)
                template_frontmatter = merge(split.backmatter, split.frontmatter)
                body = render_template(split.body, variables)
                body_source = f"template:{template_name}"
            except TemplateNotFoundError:
                # Template specified but not found - fall through to skeleton
                body = _body_for(inputs, title)
                body_source = "skeleton (template not found)"
        else:
            body = _body_for(inputs, title)

        generated_frontmatter = _frontmatter_for(inputs, today=today)
        fm = canonical_frontmatter(merge(template_frontmatter, generated_frontmatter))
        fm_text = dump_frontmatter(fm)
        content = fm_text + body

        ctx.scratchpad["content"] = content
        ctx.scratchpad["frontmatter"] = fm
        return StepResult(
            name=self.name,
            output={
                "frontmatter": fm,
                "bytes": len(content.encode("utf-8")),
                "body_source": body_source,
            },
        )

    def _resolve_template_name(self, inputs: CreateInputs, ctx: StepContext) -> str | None:
        """Determine which template to use (if any).

        Priority: explicit --template > config default for this type.
        """
        return select_template_name(
            inputs,
            config_workflows=ctx.config.workflows if ctx.config else {},
        )
