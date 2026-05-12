"""Per-step unit tests for ``pqn-daily``.

Each step is exercised in isolation through a minimal ``StepContext``.
This is the cheap layer: no disk writes, no workflow runner, just the
step's input -> output / escalation contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext
from para_quest_notes.workflows.daily.steps.check_collision import CheckCollision
from para_quest_notes.workflows.daily.steps.compose_note import ComposeNote
from para_quest_notes.workflows.daily.steps.compute_destination import ComputeDestination
from para_quest_notes.workflows.daily.steps.detect_shape import DetectShape
from para_quest_notes.workflows.daily.steps.inspect_parent import InspectParent
from para_quest_notes.workflows.daily.steps.move_file import MoveFile
from para_quest_notes.workflows.daily.steps.resolve_target import ResolveTarget
from para_quest_notes.workflows.daily.steps.validate_after import ValidateAfter


def _ctx(vault: Path | None = None, **scratch) -> StepContext:
    return StepContext(
        workflow="daily",
        run_id="test",
        vault=vault,
        scratchpad=dict(scratch),
    )


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


# ----- resolve_target -------------------------------------------------------


def test_resolve_target_finds_at_vault_root(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "2026-05-12.md"
    src.write_text("body\n")
    ctx = _ctx(vault=vault)
    res = ResolveTarget("2026-05-12").run(ctx)
    assert res.output["source"] == "2026-05-12.md"
    assert ctx.scratchpad["source_abs"] == src


def test_resolve_target_finds_in_inbox(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("body\n")
    ctx = _ctx(vault=vault)
    res = ResolveTarget("2026-05-12.md").run(ctx)
    assert res.output["source"] == "inbox/2026-05-12.md"


def test_resolve_target_finds_in_daily_notes(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    daily = vault / "resources" / "daily_notes" / "2026" / "05"
    daily.mkdir(parents=True)
    src = daily / "2026-05-12.md"
    src.write_text("body\n")
    ctx = _ctx(vault=vault)
    res = ResolveTarget("2026-05-12").run(ctx)
    assert res.output["source"] == "resources/daily_notes/2026/05/2026-05-12.md"


def test_resolve_target_explicit_path(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    (vault / "areas" / "2026-05-12.md").write_text("body\n")
    ctx = _ctx(vault=vault)
    # Explicit path wins, even outside the basename-search scope.
    res = ResolveTarget("areas/2026-05-12.md").run(ctx)
    assert res.output["source"] == "areas/2026-05-12.md"


def test_resolve_target_zero_matches(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault=vault)
    with pytest.raises(EscalateToUser) as excinfo:
        ResolveTarget("2026-05-12").run(ctx)
    assert "no daily note found" in excinfo.value.reason


def test_resolve_target_multiple_matches(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    (vault / "2026-05-12.md").write_text("body\n")
    (vault / "inbox" / "2026-05-12.md").write_text("body\n")
    ctx = _ctx(vault=vault)
    with pytest.raises(EscalateToUser) as excinfo:
        ResolveTarget("2026-05-12").run(ctx)
    assert "multiple files match" in excinfo.value.reason
    assert len(excinfo.value.options) == 2


# ----- detect_shape ---------------------------------------------------------


def test_detect_shape_ok(tmp_path: Path) -> None:
    src = tmp_path / "2026-05-12.md"
    src.write_text("")
    ctx = _ctx(source_abs=src)
    res = DetectShape().run(ctx)
    assert res.output == {"date": "2026-05-12"}
    assert ctx.scratchpad["date_iso"] == "2026-05-12"
    assert ctx.scratchpad["date_year"] == "2026"
    assert ctx.scratchpad["date_month"] == "05"


def test_detect_shape_rejects_bad_pattern(tmp_path: Path) -> None:
    src = tmp_path / "2026-05-12-notes.md"
    src.write_text("")
    ctx = _ctx(source_abs=src)
    with pytest.raises(EscalateToUser) as excinfo:
        DetectShape().run(ctx)
    assert "does not match YYYY-MM-DD" in excinfo.value.reason


def test_detect_shape_rejects_unreal_date(tmp_path: Path) -> None:
    src = tmp_path / "2026-02-31.md"
    src.write_text("")
    ctx = _ctx(source_abs=src)
    with pytest.raises(EscalateToUser) as excinfo:
        DetectShape().run(ctx)
    assert "not a real calendar date" in excinfo.value.reason


# ----- inspect_parent -------------------------------------------------------


@pytest.mark.parametrize(
    "rel,kind",
    [
        ("2026-05-12.md", "vault_root"),
        ("inbox/2026-05-12.md", "inbox"),
        ("inbox/sub/2026-05-12.md", "inbox"),
        ("resources/daily_notes/2026/05/2026-05-12.md", "daily_notes"),
    ],
)
def test_inspect_parent_allows(rel: str, kind: str) -> None:
    ctx = _ctx(source_rel=rel)
    res = InspectParent().run(ctx)
    assert res.output == {"parent_kind": kind}


@pytest.mark.parametrize(
    "rel,top",
    [
        ("projects/X/2026-05-12.md", "projects"),
        ("areas/Home/2026-05-12.md", "areas"),
        ("archive/projects/2026-05-12.md", "archive"),
        ("resources/notes/2026-05-12.md", "resources"),
    ],
)
def test_inspect_parent_escalates(rel: str, top: str) -> None:
    ctx = _ctx(source_rel=rel)
    with pytest.raises(EscalateToUser) as excinfo:
        InspectParent().run(ctx)
    assert f"under {top}/" in excinfo.value.reason


# ----- compute_destination --------------------------------------------------


def test_compute_destination_from_inbox(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("")
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        source_rel="inbox/2026-05-12.md",
        date_iso="2026-05-12",
        date_year="2026",
        date_month="05",
    )
    res = ComputeDestination().run(ctx)
    assert res.output["destination"] == "resources/daily_notes/2026/05/2026-05-12.md"
    assert res.output["already_at_destination"] is False


def test_compute_destination_already_at_canonical(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    daily = vault / "resources" / "daily_notes" / "2026" / "05"
    daily.mkdir(parents=True)
    src = daily / "2026-05-12.md"
    src.write_text("")
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        source_rel="resources/daily_notes/2026/05/2026-05-12.md",
        date_iso="2026-05-12",
        date_year="2026",
        date_month="05",
    )
    res = ComputeDestination().run(ctx)
    assert res.output["already_at_destination"] is True


# ----- check_collision ------------------------------------------------------


def test_check_collision_skips_when_already_at_destination(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "2026-05-12.md"
    src.write_text("")
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        destination_abs=src,
        destination_rel="2026-05-12.md",
        date_iso="2026-05-12",
        already_at_destination=True,
    )
    res = CheckCollision().run(ctx)
    assert res.output["skipped"] is True


def test_check_collision_destination_exists(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("a\n")
    daily = vault / "resources" / "daily_notes" / "2026" / "05"
    daily.mkdir(parents=True)
    dest = daily / "2026-05-12.md"
    dest.write_text("b\n")
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        destination_abs=dest,
        destination_rel="resources/daily_notes/2026/05/2026-05-12.md",
        date_iso="2026-05-12",
        already_at_destination=False,
    )
    with pytest.raises(EscalateToUser) as excinfo:
        CheckCollision().run(ctx)
    assert "destination already exists" in excinfo.value.reason


def test_check_collision_ignores_self(tmp_path: Path) -> None:
    """Source basename must not collide with itself."""
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("a\n")
    dest = vault / "resources" / "daily_notes" / "2026" / "05" / "2026-05-12.md"
    # dest does not exist yet.
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        destination_abs=dest,
        destination_rel="resources/daily_notes/2026/05/2026-05-12.md",
        date_iso="2026-05-12",
        already_at_destination=False,
    )
    res = CheckCollision().run(ctx)
    assert res.output["skipped"] is False
    assert res.output["collisions"] == []


def test_check_collision_basename_collision_elsewhere(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("a\n")
    # Stray file with same basename somewhere unexpected.
    stray = vault / "areas" / "2026-05-12.md"
    stray.write_text("b\n")
    dest = vault / "resources" / "daily_notes" / "2026" / "05" / "2026-05-12.md"
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        destination_abs=dest,
        destination_rel="resources/daily_notes/2026/05/2026-05-12.md",
        date_iso="2026-05-12",
        already_at_destination=False,
    )
    with pytest.raises(EscalateToUser) as excinfo:
        CheckCollision().run(ctx)
    assert "basename collides" in excinfo.value.reason


# ----- compose_note ---------------------------------------------------------


def test_compose_note_inserts_h1_when_missing(tmp_path: Path) -> None:
    src = tmp_path / "2026-05-12.md"
    src.write_text("- [ ] task\n")
    ctx = _ctx(source_abs=src, date_iso="2026-05-12", already_at_destination=False)
    res = ComposeNote().run(ctx)
    assert res.output["h1_inserted"] is True
    assert ctx.scratchpad["content"] == "# 2026-05-12\n\n- [ ] task\n"


def test_compose_note_preserves_existing_h1(tmp_path: Path) -> None:
    src = tmp_path / "2026-05-12.md"
    src.write_text("# Daily — May 12\n\nbody\n")
    ctx = _ctx(source_abs=src, date_iso="2026-05-12", already_at_destination=False)
    res = ComposeNote().run(ctx)
    assert res.output["h1_inserted"] is False
    assert ctx.scratchpad["content"] == "# Daily — May 12\n\nbody\n"


def test_compose_note_preserves_user_frontmatter(tmp_path: Path) -> None:
    src = tmp_path / "2026-05-12.md"
    src.write_text("---\nfoo: bar\n---\nbody\n")
    ctx = _ctx(source_abs=src, date_iso="2026-05-12", already_at_destination=False)
    res = ComposeNote().run(ctx)
    assert res.output["frontmatter_migrated"] is False
    assert "foo: bar" in ctx.scratchpad["content"]
    assert "# 2026-05-12" in ctx.scratchpad["content"]


def test_compose_note_migrates_backmatter(tmp_path: Path) -> None:
    src = tmp_path / "2026-05-12.md"
    src.write_text("# 2026-05-12\n\nbody\n\n---\nfoo: bar\n---\n")
    ctx = _ctx(source_abs=src, date_iso="2026-05-12", already_at_destination=False)
    res = ComposeNote().run(ctx)
    assert res.output["frontmatter_migrated"] is True
    content = ctx.scratchpad["content"]
    assert content.startswith("---\nfoo: bar\n---\n")
    # The tail fence must be gone.
    assert content.count("---") == 2


def test_compose_note_idempotent_at_destination(tmp_path: Path) -> None:
    src = tmp_path / "2026-05-12.md"
    src.write_text("# 2026-05-12\n\nbody\n")
    ctx = _ctx(source_abs=src, date_iso="2026-05-12", already_at_destination=True)
    res = ComposeNote().run(ctx)
    assert res.output["content_changed"] is False


# ----- move_file ------------------------------------------------------------


def test_move_file_dry_run(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("body\n")
    dest = vault / "resources" / "daily_notes" / "2026" / "05" / "2026-05-12.md"
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        destination_abs=dest,
        destination_rel="resources/daily_notes/2026/05/2026-05-12.md",
        content="# 2026-05-12\n\nbody\n",
        content_changed=True,
        already_at_destination=False,
    )
    res = MoveFile(apply=False).run(ctx)
    assert res.output["moved"] is False
    assert src.exists()
    assert not dest.exists()


def test_move_file_apply_writes_then_unlinks(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("body\n")
    dest = vault / "resources" / "daily_notes" / "2026" / "05" / "2026-05-12.md"
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        destination_abs=dest,
        destination_rel="resources/daily_notes/2026/05/2026-05-12.md",
        content="# 2026-05-12\n\nbody\n",
        content_changed=True,
        already_at_destination=False,
    )
    res = MoveFile(apply=True).run(ctx)
    assert res.output["moved"] is True
    assert not src.exists()
    assert dest.read_text() == "# 2026-05-12\n\nbody\n"


def test_move_file_apply_already_at_destination_noop(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    daily = vault / "resources" / "daily_notes" / "2026" / "05"
    daily.mkdir(parents=True)
    src = daily / "2026-05-12.md"
    src.write_text("# 2026-05-12\n\nbody\n")
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        destination_abs=src,
        destination_rel="resources/daily_notes/2026/05/2026-05-12.md",
        content="# 2026-05-12\n\nbody\n",
        content_changed=False,
        already_at_destination=True,
    )
    res = MoveFile(apply=True).run(ctx)
    assert res.output["moved"] is False
    assert src.read_text() == "# 2026-05-12\n\nbody\n"


def test_move_file_apply_already_at_destination_rewrites(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    daily = vault / "resources" / "daily_notes" / "2026" / "05"
    daily.mkdir(parents=True)
    src = daily / "2026-05-12.md"
    src.write_text("body\n")
    new_content = "# 2026-05-12\n\nbody\n"
    ctx = _ctx(
        vault=vault,
        source_abs=src,
        destination_abs=src,
        destination_rel="resources/daily_notes/2026/05/2026-05-12.md",
        content=new_content,
        content_changed=True,
        already_at_destination=True,
    )
    res = MoveFile(apply=True).run(ctx)
    assert res.output["moved"] is False
    assert res.output["rewrote_in_place"] is True
    assert src.read_text() == new_content


# ----- validate_after -------------------------------------------------------


def test_validate_after_dry_run_skips(tmp_path: Path) -> None:
    ctx = _ctx(vault=tmp_path)
    res = ValidateAfter(apply=False).run(ctx)
    assert res.output["skipped"] is True
