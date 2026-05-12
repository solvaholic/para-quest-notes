"""Step 8: validate_after (pure, no-op on dry-run).

Same shape as pqn-create's ``validate_after``: on apply, scope
``validate.api.validate_paths`` to the new archive path. Whole-vault
validation stays the user's call (run ``pqn-validate``).
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.validate.api import validate_paths


class ValidateAfter:
    name = "validate_after"

    def __init__(self, *, apply: bool):
        self.apply = apply

    def run(self, ctx: StepContext) -> StepResult:
        if not self.apply or ctx.vault is None:
            return StepResult(
                name=self.name,
                output={"skipped": True, "issues": []},
                meta={"applied": self.apply},
            )
        dest_abs: Path = ctx.scratchpad["destination_abs"]
        if not dest_abs.exists():
            return StepResult(
                name=self.name,
                output={"skipped": True, "issues": []},
                meta={"reason": "destination missing after move"},
            )
        report = validate_paths(ctx.vault, [dest_abs])
        issues_payload = [
            {
                "check": i.check,
                "severity": i.severity,
                "path": i.path,
                "message": i.message,
            }
            for i in report.issues
        ]
        return StepResult(
            name=self.name,
            output={"skipped": False, "issues": issues_payload},
            meta={"issue_count": len(issues_payload)},
        )
