"""Focused tests for the managed daily task-roundup step."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext
from para_quest_notes.workflows.daily.steps.compose_task_roundup import (
    END_MARKER,
    START_MARKER,
    ComposeTaskRoundup,
)

DATE_FIELDS = ["due", "scheduled", "start"]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    _write(
        vault / "projects" / "Build Raised Beds.md",
        "# Build Raised Beds\n\n"
        "- [ ] Order soil 📅 2026-09-06\n"
        "- [/] Call supplier ⏳ 2026-09-07\n"
        "- [ ] Install edging 📅 2026-09-10\n",
    )
    return vault


def _run(vault: Path, content: str, *, apply: bool = False):
    ctx = StepContext(
        workflow="daily",
        run_id="test",
        vault=vault,
        scratchpad={
            "date_iso": "2026-09-07",
            "content": content,
            "content_changed": False,
        },
    )
    result = ComposeTaskRoundup(date_fields=DATE_FIELDS, apply=apply).run(ctx)
    return result, ctx


def test_inserts_embedded_report_and_preserves_user_content(tmp_path: Path) -> None:
    original = "# 2026-09-07\n\n## Tasks\n\n- [ ] User-owned task\n\nMorning notes.\n"

    result, ctx = _run(_vault(tmp_path), original)

    assert result.output["action"] == "insert"
    assert result.output["applied"] is False
    assert result.output["reference_date"] == "2026-09-07"
    assert result.output["summary"] == {
        "total": 3,
        "overdue": 1,
        "due_today": 1,
        "upcoming": 1,
        "unscheduled": 0,
    }
    assert ctx.scratchpad["content"].startswith(original + "\n" + START_MARKER)
    assert "### Overdue (1)" in ctx.scratchpad["content"]
    assert "- [[Build Raised Beds]] Order soil (due 2026-09-06)" in ctx.scratchpad["content"]
    assert "## Tasks\n\n- [ ] User-owned task" in ctx.scratchpad["content"]
    assert "- [ ]" not in ctx.scratchpad["content"].split(START_MARKER, 1)[1]
    assert ctx.scratchpad["content"].endswith(END_MARKER + "\n")
    assert ctx.scratchpad["content_changed"] is True


def test_replaces_only_managed_region(tmp_path: Path) -> None:
    content = f"# 2026-09-07\n\nBefore.\n\n{START_MARKER}\n## stale\n{END_MARKER}\n\nAfter.\n"

    result, ctx = _run(_vault(tmp_path), content, apply=True)

    assert result.output["action"] == "replace"
    assert result.output["applied"] is True
    assert ctx.scratchpad["content"].startswith("# 2026-09-07\n\nBefore.\n\n" + START_MARKER)
    assert ctx.scratchpad["content"].endswith(END_MARKER + "\n\nAfter.\n")
    assert "## stale" not in ctx.scratchpad["content"]


def test_preserves_frontmatter_and_bytes_around_replaced_region(tmp_path: Path) -> None:
    prefix = "---\ncustom: value\n---\n# 2026-09-07\n\nBefore.\n\n"
    suffix = "\nAfter.\n"
    content = prefix + START_MARKER + "\nstale\n" + END_MARKER + suffix

    _, ctx = _run(_vault(tmp_path), content)

    assert ctx.scratchpad["content"].startswith(prefix + START_MARKER)
    assert ctx.scratchpad["content"].endswith(END_MARKER + suffix)


def test_second_run_is_byte_idempotent(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    _, first = _run(vault, "# 2026-09-07\n\n")
    generated = first.scratchpad["content"]

    result, second = _run(vault, generated, apply=True)

    assert result.output["action"] == "unchanged"
    assert second.scratchpad["content"] == generated
    assert second.scratchpad["content_changed"] is False


def test_marker_looking_text_inside_fences_is_ignored(tmp_path: Path) -> None:
    content = (
        "# 2026-09-07\n\n"
        "```markdown\n"
        f"{START_MARKER}\n"
        "example\n"
        f"{END_MARKER}\n"
        "```\n\n"
        "~~~\n"
        f"{START_MARKER}\n"
        f"{END_MARKER}\n"
        "~~~\n"
    )

    result, ctx = _run(_vault(tmp_path), content)

    assert result.output["action"] == "insert"
    assert ctx.scratchpad["content"].count(START_MARKER) == 3
    assert ctx.scratchpad["content"].count(END_MARKER) == 3


def test_shorter_fence_does_not_expose_markers(tmp_path: Path) -> None:
    content = f"# 2026-09-07\n\n````markdown\n```\n{START_MARKER}\n{END_MARKER}\n````\n"

    result, ctx = _run(_vault(tmp_path), content)

    assert result.output["action"] == "insert"
    assert ctx.scratchpad["content"].count(START_MARKER) == 2
    assert ctx.scratchpad["content"].count(END_MARKER) == 2


@pytest.mark.parametrize("fence", ["    ```", "\t```", "```invalid`info"])
def test_invalid_fence_openers_do_not_hide_real_markers(fence: str, tmp_path: Path) -> None:
    content = f"# 2026-09-07\n\n{fence}\n{START_MARKER}\nstale\n{END_MARKER}\n"

    result, ctx = _run(_vault(tmp_path), content)

    assert result.output["action"] == "replace"
    assert ctx.scratchpad["content"].count(START_MARKER) == 1
    assert ctx.scratchpad["content"].count(END_MARKER) == 1
    assert "stale" not in ctx.scratchpad["content"]


def test_over_indented_closing_fence_does_not_expose_markers(tmp_path: Path) -> None:
    content = f"# 2026-09-07\n\n````\n    ````\n{START_MARKER}\n{END_MARKER}\n````\n"

    result, ctx = _run(_vault(tmp_path), content)

    assert result.output["action"] == "insert"
    assert ctx.scratchpad["content"].count(START_MARKER) == 2
    assert ctx.scratchpad["content"].count(END_MARKER) == 2


@pytest.mark.parametrize("fence", ["```markdown", "~~~text"])
def test_unclosed_fence_escalates_instead_of_hiding_appended_region(
    fence: str,
    tmp_path: Path,
) -> None:
    content = f"# 2026-09-07\n\n{fence}\nunclosed example\n"

    with pytest.raises(EscalateToUser, match="unclosed fenced code block"):
        _run(_vault(tmp_path), content)


@pytest.mark.parametrize(
    "body",
    [
        f"{START_MARKER}\nmissing end\n",
        f"{END_MARKER}\nmissing start\n",
        f"{END_MARKER}\n{START_MARKER}\n",
        f"{START_MARKER}\n{START_MARKER}\n{END_MARKER}\n",
        f"{START_MARKER}\n{END_MARKER}\n{START_MARKER}\n{END_MARKER}\n",
    ],
)
def test_ambiguous_markers_escalate(body: str, tmp_path: Path) -> None:
    with pytest.raises(EscalateToUser, match="managed task-roundup markers"):
        _run(_vault(tmp_path), "# 2026-09-07\n\n" + body)


def test_empty_report_keeps_managed_region(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write(vault / "projects" / "No Tasks.md", "# No Tasks\n")

    result, ctx = _run(vault, "# 2026-09-07\n\n")

    assert result.output["action"] == "insert"
    assert result.output["summary"]["total"] == 0
    assert "tasks" not in result.output
    assert result.meta == {"action": "insert", "tasks": 0}
    assert "No open tasks due." in ctx.scratchpad["content"]
    assert START_MARKER in ctx.scratchpad["content"]
    assert END_MARKER in ctx.scratchpad["content"]
