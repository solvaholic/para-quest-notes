"""Step 1: validate_inputs (pure).

Confirms the user-supplied inputs satisfy the PARA + Quest schema and
Rule 1 (notes that will carry tasks must declare at least one Quest in
``supports``).

Without an LLM in the loop, escalation here is "the CLI invocation is
missing or malformed" rather than "I can't decide." The user fixes the
flags and re-runs.
"""

from __future__ import annotations

import re

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.create.contract import CreateInputs

# Same character class pqn-ingest's propose_filename uses for filename
# validation. We apply it here to the *title* so we fail fast before
# composing a path that would trip validate_after.
_TITLE_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-()'.,&]*$")
_INTERIOR_CAPS = re.compile(r"[a-z][A-Z]")
_WIKILINK = re.compile(r"^\[\[[^\[\]|]+\]\]$")

_PARA_TYPES = ("project", "area", "resource")
_QUEST_KINDS = ("main", "side", "none")


class ValidateInputs:
    name = "validate_inputs"

    def __init__(self, inputs: CreateInputs):
        self.inputs = inputs

    def run(self, ctx: StepContext) -> StepResult:
        i = self.inputs

        if i.type not in _PARA_TYPES:
            raise EscalateToUser(
                step=self.name,
                reason=f"--type must be one of {_PARA_TYPES}, got {i.type!r}",
                options=[{"type": t} for t in _PARA_TYPES],
                context={},
            )
        if i.quest not in _QUEST_KINDS:
            raise EscalateToUser(
                step=self.name,
                reason=f"--quest must be one of {_QUEST_KINDS}, got {i.quest!r}",
                options=[{"quest": q} for q in _QUEST_KINDS],
                context={},
            )

        title = i.title.strip()
        if not title:
            raise EscalateToUser(
                step=self.name,
                reason="--title is required",
                options=[],
                context={},
            )
        if not _TITLE_OK.match(title):
            raise EscalateToUser(
                step=self.name,
                reason="--title has disallowed characters; use Title Case "
                "(letters, digits, spaces, and -()'.,& only)",
                options=[],
                context={"title": title},
            )
        if _INTERIOR_CAPS.search(title):
            raise EscalateToUser(
                step=self.name,
                reason="--title looks like camelCase or PascalCase; "
                "use Title Case (words separated by spaces)",
                options=[],
                context={"title": title},
            )

        for s in i.supports:
            if not _WIKILINK.match(s):
                raise EscalateToUser(
                    step=self.name,
                    reason="--supports entries must be wikilinks like "
                    "'[[Quest Name]]' (no aliases, no headings)",
                    options=[],
                    context={"supports": list(i.supports), "offender": s},
                )

        # Rule 1: Projects always carry tasks → must declare supports.
        # Areas may or may not; we don't have an LLM to decide, so we
        # require supports for areas too. A future --no-tasks flag can
        # relax this for taskless Areas.
        if i.type in ("project", "area") and not i.supports:
            raise EscalateToUser(
                step=self.name,
                reason=f"--supports is required for type={i.type!r} "
                "(Rule 1: notes with tasks must support 1+ Quests)",
                options=[],
                context={"type": i.type, "title": title},
            )
        if i.type == "resource" and i.quest != "none":
            raise EscalateToUser(
                step=self.name,
                reason="resources should have quest=none (set --quest none)",
                options=[],
                context={"quest": i.quest},
            )

        if i.sub_path is not None:
            sp = i.sub_path.strip().strip("/")
            if sp.startswith("..") or "/.." in sp or "\\" in sp:
                raise EscalateToUser(
                    step=self.name,
                    reason="--sub-path must be a relative path under the PARA "
                    "directory (no '..', no backslashes)",
                    options=[],
                    context={"sub_path": i.sub_path},
                )
            ctx.scratchpad["sub_path"] = sp
        else:
            ctx.scratchpad["sub_path"] = ""

        ctx.scratchpad["title"] = title
        ctx.scratchpad["inputs"] = i
        return StepResult(name=self.name, output={"title": title, "type": i.type})
