"""Step 3: inspect_parent (pure).

Examine the source's vault-relative parent. Allowed homes:

* vault root (loose, just dropped there)
* ``inbox/`` at any depth
* ``resources/daily_notes/`` at any depth (already filed; re-filing
  with H1 / backmatter cleanup is fine)

Anything else (``projects/``, ``areas/``, ``archive/``, other
``resources/<...>/``) implies the file lives somewhere PARA-meaningful
and shouldn't be silently relocated by ``pqn-daily``. Escalate so the
user can decide whether it really is a daily note.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult


class InspectParent:
    name = "inspect_parent"

    def run(self, ctx: StepContext) -> StepResult:
        if ctx.scratchpad.get("creating_missing", False):
            return StepResult(
                name=self.name,
                output={"parent_kind": "missing"},
                meta={"creating_missing": True},
            )
        source_rel: str = ctx.scratchpad["source_rel"]
        rel = PurePosixPath(source_rel)
        parts = rel.parts

        # parts = (..., basename). The directory parts are parts[:-1].
        dir_parts = parts[:-1]

        if len(dir_parts) == 0:
            kind = "vault_root"
        elif dir_parts[0] == "inbox":
            kind = "inbox"
        elif len(dir_parts) >= 2 and dir_parts[0] == "resources" and dir_parts[1] == "daily_notes":
            kind = "daily_notes"
        else:
            top = dir_parts[0]
            raise EscalateToUser(
                step=self.name,
                reason=(
                    f"source is under {top}/; pqn-daily files daily notes only "
                    "(move it manually if it really is a daily note)"
                ),
                options=[],
                context={"source": source_rel},
            )

        ctx.scratchpad["parent_kind"] = kind
        return StepResult(
            name=self.name,
            output={"parent_kind": kind},
            meta={"parent_kind": kind},
        )
