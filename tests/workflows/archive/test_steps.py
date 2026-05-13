"""Per-step tests for ``pqn-archive``."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext
from para_quest_notes.vault.frontmatter import split_note
from para_quest_notes.workflows.archive.steps.compose_archive import ComposeArchive
from para_quest_notes.workflows.archive.steps.decide_task_action import DecideTaskAction
from para_quest_notes.workflows.archive.steps.prepare_outcome import PrepareOutcome
from para_quest_notes.workflows.archive.steps.resolve_target import ResolveTarget
from para_quest_notes.workflows.archive.steps.scan_open_tasks import (
    ScanOpenTasks,
    find_open_tasks,
)
from para_quest_notes.workflows.archive.steps.verify_project import VerifyProject
from para_quest_notes.workflows.archive.steps.write_and_move import WriteAndMove


def _ctx(vault: Path | None = None) -> StepContext:
    return StepContext(workflow="archive", run_id="test", vault=vault)


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


# ---- resolve_target ----------------------------------------------------


def test_resolve_target_by_basename(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "Brew Setup.md").write_text("---\ntype: project\n---\n")
    ctx = _ctx(vault)
    ResolveTarget("Brew Setup").run(ctx)
    assert ctx.scratchpad["source_rel"] == "projects/Brew Setup.md"


def test_resolve_target_by_path(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "nested").mkdir()
    (vault / "projects" / "nested" / "X.md").write_text("---\ntype: project\n---\n")
    ctx = _ctx(vault)
    ResolveTarget("projects/nested/X.md").run(ctx)
    assert ctx.scratchpad["source_rel"] == "projects/nested/X.md"


def test_resolve_target_missing_escalates(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    with pytest.raises(EscalateToUser) as exc:
        ResolveTarget("Nope").run(_ctx(vault))
    assert "no Project note" in exc.value.reason


def test_resolve_target_ambiguous_escalates(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "a").mkdir()
    (vault / "projects" / "b").mkdir()
    (vault / "projects" / "a" / "X.md").write_text("---\ntype: project\n---\n")
    (vault / "projects" / "b" / "X.md").write_text("---\ntype: project\n---\n")
    with pytest.raises(EscalateToUser) as exc:
        ResolveTarget("X").run(_ctx(vault))
    assert "multiple" in exc.value.reason


def test_resolve_target_rejects_non_projects(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "areas" / "Home.md").write_text("---\ntype: area\n---\n")
    with pytest.raises(EscalateToUser) as exc:
        ResolveTarget("areas/Home.md").run(_ctx(vault))
    assert "Projects only" in exc.value.reason


# ---- verify_project ----------------------------------------------------


def test_verify_project_happy(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text("---\ntype: project\nquest: none\n---\nbody\n")
    ctx = _ctx(vault)
    ctx.scratchpad.update(source_abs=src, source_rel="projects/X.md")
    VerifyProject().run(ctx)
    assert ctx.scratchpad["split"].frontmatter["type"] == "project"


def test_verify_project_rejects_area(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text("---\ntype: area\n---\nbody\n")
    ctx = _ctx(vault)
    ctx.scratchpad.update(source_abs=src, source_rel="projects/X.md")
    with pytest.raises(EscalateToUser) as exc:
        VerifyProject().run(ctx)
    assert "Projects only" in exc.value.reason


def test_verify_project_accepts_legacy_backmatter(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text("# X\nbody\n\n---\ntype: project\nquest: none\n---\n")
    ctx = _ctx(vault)
    ctx.scratchpad.update(source_abs=src, source_rel="projects/X.md")
    VerifyProject().run(ctx)
    assert ctx.scratchpad["split"].had_backmatter is True


# ---- scan_open_tasks ---------------------------------------------------


def test_find_open_tasks_basic():
    body = "intro\n- [ ] one\n- [/] two\n- [x] done\n- [-] cancelled\n"
    tasks = find_open_tasks(body)
    assert [t["line"] for t in tasks] == [2, 3]
    assert [t["state"] for t in tasks] == [" ", "/"]


def test_find_open_tasks_skips_fenced():
    body = "```\n- [ ] not a task\n```\n- [ ] real\n"
    tasks = find_open_tasks(body)
    assert len(tasks) == 1
    assert tasks[0]["line"] == 4


def test_find_open_tasks_skips_tilde_fenced():
    body = "~~~\n- [ ] not a task\n~~~\n- [ ] real\n"
    tasks = find_open_tasks(body)
    assert len(tasks) == 1


# ---- decide_task_action ------------------------------------------------


def test_decide_task_action_clean_proceeds():
    ctx = _ctx()
    ctx.scratchpad.update(open_tasks=[], source_rel="projects/X.md")
    res = DecideTaskAction(cancel_open_tasks=False).run(ctx)
    assert res.output["open_tasks"] == 0
    assert ctx.scratchpad["will_cancel_tasks"] is False


def test_decide_task_action_escalates_without_flag():
    ctx = _ctx()
    ctx.scratchpad.update(
        open_tasks=[{"line": 2, "state": " ", "text": "x", "bullet": "- "}],
        source_rel="projects/X.md",
    )
    with pytest.raises(EscalateToUser):
        DecideTaskAction(cancel_open_tasks=False).run(ctx)


def test_decide_task_action_with_flag_will_cancel():
    ctx = _ctx()
    ctx.scratchpad.update(
        open_tasks=[{"line": 2, "state": " ", "text": "x", "bullet": "- "}],
        source_rel="projects/X.md",
    )
    DecideTaskAction(cancel_open_tasks=True).run(ctx)
    assert ctx.scratchpad["will_cancel_tasks"] is True


# ---- prepare_outcome ---------------------------------------------------


def test_prepare_outcome_keeps_existing():
    ctx = _ctx()
    ctx.scratchpad["split"] = split_note("body\n\n## Outcome\nold text\n")
    ctx.scratchpad["source_rel"] = "projects/X.md"
    PrepareOutcome(outcome=None).run(ctx)
    assert ctx.scratchpad["outcome_action"] == "kept"


def test_prepare_outcome_marks_provided_when_supplied():
    ctx = _ctx()
    ctx.scratchpad["split"] = split_note("body only\n")
    ctx.scratchpad["source_rel"] = "projects/X.md"
    PrepareOutcome(outcome="Shipped").run(ctx)
    assert ctx.scratchpad["outcome_action"] == "provided"
    assert ctx.scratchpad["outcome_text"] == "Shipped"


def test_prepare_outcome_marks_will_generate_on_dry_run():
    ctx = _ctx()
    ctx.scratchpad["split"] = split_note("body only\n")
    ctx.scratchpad["source_rel"] = "projects/X.md"
    PrepareOutcome(outcome=None, generate_outcome=True, apply=False).run(ctx)
    assert ctx.scratchpad["outcome_action"] == "will_generate"
    assert ctx.scratchpad["needs_generate_outcome"] is False


def test_prepare_outcome_requests_generation_on_apply():
    ctx = _ctx()
    ctx.scratchpad["split"] = split_note("body only\n")
    ctx.scratchpad["source_rel"] = "projects/X.md"
    res = PrepareOutcome(outcome=None, generate_outcome=True, apply=True).run(ctx)
    assert res.output["action"] == "generate_requested"
    assert ctx.scratchpad["needs_generate_outcome"] is True


def test_prepare_outcome_escalates_when_missing():
    ctx = _ctx()
    ctx.scratchpad["split"] = split_note("body only\n")
    ctx.scratchpad["source_rel"] = "projects/X.md"
    with pytest.raises(EscalateToUser):
        PrepareOutcome(outcome=None).run(ctx)
    assert ctx.scratchpad["outcome_action"] == "required"


# ---- compose_archive ---------------------------------------------------


def _compose_ctx(tmp_path: Path, source_text: str, **overrides):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text(source_text)
    split = split_note(source_text)
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        source_abs=src,
        source_rel="projects/X.md",
        split=split,
        open_tasks=find_open_tasks(split.body),
        will_cancel_tasks=False,
        outcome_action="kept",
        outcome_text=None,
    )
    ctx.scratchpad.update(overrides)
    return ctx, src


def test_compose_archive_basic(tmp_path: Path):
    ctx, _ = _compose_ctx(
        tmp_path,
        "---\ntype: project\nquest: none\n---\n# X\n\n## Outcome\ndone\n",
    )
    ComposeArchive(today="2026-05-12").run(ctx)
    content = ctx.scratchpad["content"]
    assert "type: project" in content
    assert "## Outcome" in content
    assert ctx.scratchpad["destination_rel"] == "archive/projects/X.md"
    assert ctx.scratchpad["tasks_cancelled"] == 0
    assert ctx.scratchpad["frontmatter_migrated"] is False


def test_compose_archive_cancels_tasks(tmp_path: Path):
    ctx, _ = _compose_ctx(
        tmp_path,
        "---\ntype: project\nquest: none\n---\nintro\n- [ ] one\n- [/] two\n",
        will_cancel_tasks=True,
        outcome_action="provided",
        outcome_text="Shipped it",
    )
    ctx.scratchpad["open_tasks"] = find_open_tasks(ctx.scratchpad["split"].body)
    ComposeArchive(today="2026-05-12").run(ctx)
    content = ctx.scratchpad["content"]
    assert "- [-] one ❌ 2026-05-12" in content
    assert "- [-] two ❌ 2026-05-12" in content
    assert ctx.scratchpad["tasks_cancelled"] == 2
    assert "## Outcome\n\nShipped it" in content


def test_compose_archive_preserves_block_id(tmp_path: Path):
    ctx, _ = _compose_ctx(
        tmp_path,
        "---\ntype: project\nquest: none\n---\n- [ ] do thing ^abc123\n",
        will_cancel_tasks=True,
        outcome_action="kept",
    )
    ctx.scratchpad["open_tasks"] = find_open_tasks(ctx.scratchpad["split"].body)
    ComposeArchive(today="2026-05-12").run(ctx)
    content = ctx.scratchpad["content"]
    assert "- [-] do thing ❌ 2026-05-12 ^abc123" in content


def test_compose_archive_escalates_on_tasks_metadata(tmp_path: Path):
    ctx, _ = _compose_ctx(
        tmp_path,
        "---\ntype: project\nquest: none\n---\n- [ ] do thing 📅 2026-06-01\n",
        will_cancel_tasks=True,
        outcome_action="kept",
    )
    ctx.scratchpad["open_tasks"] = find_open_tasks(ctx.scratchpad["split"].body)
    with pytest.raises(EscalateToUser):
        ComposeArchive(today="2026-05-12").run(ctx)


def test_compose_archive_migrates_backmatter(tmp_path: Path):
    ctx, _ = _compose_ctx(
        tmp_path,
        "# X\n\nbody\n\n---\ntype: project\nquest: none\n---\n",
        outcome_action="provided",
        outcome_text="done",
    )
    ComposeArchive(today="2026-05-12").run(ctx)
    content = ctx.scratchpad["content"]
    assert content.startswith("---\ntype: project")
    assert content.count("---\n") == 2  # leading fence only, no tail
    assert ctx.scratchpad["frontmatter_migrated"] is True


def test_compose_archive_mirrors_subpath(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "foo" / "bar").mkdir(parents=True)
    src = vault / "projects" / "foo" / "bar" / "X.md"
    src.write_text("---\ntype: project\nquest: none\n---\n## Outcome\nx\n")
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        source_abs=src,
        source_rel="projects/foo/bar/X.md",
        split=split_note(src.read_text()),
        open_tasks=[],
        will_cancel_tasks=False,
        outcome_action="kept",
        outcome_text=None,
    )
    ComposeArchive(today="2026-05-12").run(ctx)
    assert ctx.scratchpad["destination_rel"] == "archive/projects/foo/bar/X.md"


# ---- write_and_move ----------------------------------------------------


def test_write_and_move_dry_run_no_side_effects(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text("---\ntype: project\n---\n")
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        source_abs=src,
        destination_abs=vault / "archive" / "projects" / "X.md",
        destination_rel="archive/projects/X.md",
        content="new content",
    )
    WriteAndMove(apply=False).run(ctx)
    assert src.exists()
    assert not (vault / "archive" / "projects" / "X.md").exists()


def test_write_and_move_apply_writes_and_removes_source(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text("---\ntype: project\n---\n")
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        source_abs=src,
        destination_abs=vault / "archive" / "projects" / "X.md",
        destination_rel="archive/projects/X.md",
        content="archived content",
    )
    WriteAndMove(apply=True).run(ctx)
    assert not src.exists()
    dest = vault / "archive" / "projects" / "X.md"
    assert dest.exists()
    assert dest.read_text() == "archived content"


def test_write_and_move_refuses_to_overwrite(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text("a")
    dest = vault / "archive" / "projects" / "X.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("preexisting")
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        source_abs=src,
        destination_abs=dest,
        destination_rel="archive/projects/X.md",
        content="new",
    )
    with pytest.raises(EscalateToUser):
        WriteAndMove(apply=True).run(ctx)
    assert src.exists()
    assert dest.read_text() == "preexisting"


# ---- ScanOpenTasks runner ----------------------------------------------


def test_scan_open_tasks_step_populates_scratchpad(tmp_path: Path):
    ctx = _ctx()
    ctx.scratchpad["split"] = split_note("- [ ] one\n- [x] done\n")
    res = ScanOpenTasks().run(ctx)
    assert res.output["count"] == 1
