"""End-to-end pipeline tests for ``pqn-daily``."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest

from para_quest_notes.workflows.daily.contract import DailyInputs
from para_quest_notes.workflows.daily.pipeline import file_daily_note
from para_quest_notes.workflows.daily.steps.compose_task_roundup import (
    END_MARKER,
    START_MARKER,
)
from para_quest_notes.workflows.validate.api import validate_paths


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def test_dry_run_files_inbox_daily(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("- [ ] thing\n")
    res = file_daily_note(DailyInputs(target="2026-05-12"), vault=vault, apply=False)
    assert res.ok and res.escalation is None
    assert res.moved is False  # dry-run
    assert res.plan.source == "inbox/2026-05-12.md"
    assert res.plan.destination == "resources/daily_notes/2026/05/2026-05-12.md"
    assert res.plan.h1_inserted is True
    assert src.exists()  # untouched on dry-run


def test_apply_files_inbox_daily(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("- [ ] thing\n")
    res = file_daily_note(DailyInputs(target="2026-05-12"), vault=vault, apply=True)
    assert res.ok
    assert res.moved is True
    dest = vault / "resources" / "daily_notes" / "2026" / "05" / "2026-05-12.md"
    assert dest.exists()
    assert not src.exists()
    assert dest.read_text() == "# 2026-05-12\n\n- [ ] thing\n"


def test_apply_idempotent_rerun(tmp_path: Path) -> None:
    """Running pqn-daily on an already-filed note is a no-op success."""
    vault = _seed_vault(tmp_path)
    daily = vault / "resources" / "daily_notes" / "2026" / "05"
    daily.mkdir(parents=True)
    dest = daily / "2026-05-12.md"
    dest.write_text("# 2026-05-12\n\nbody\n")
    res = file_daily_note(DailyInputs(target="2026-05-12"), vault=vault, apply=True)
    assert res.ok
    assert res.moved is False
    assert res.plan.already_at_destination is True
    assert dest.read_text() == "# 2026-05-12\n\nbody\n"


def test_apply_rewrites_in_place_when_h1_missing(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    daily = vault / "resources" / "daily_notes" / "2026" / "05"
    daily.mkdir(parents=True)
    dest = daily / "2026-05-12.md"
    dest.write_text("body\n")
    res = file_daily_note(DailyInputs(target="2026-05-12"), vault=vault, apply=True)
    assert res.ok
    assert res.plan.already_at_destination is True
    assert res.plan.h1_inserted is True
    assert dest.read_text() == "# 2026-05-12\n\nbody\n"


def test_escalates_on_bad_filename(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    (vault / "inbox" / "not-a-date.md").write_text("")
    res = file_daily_note(DailyInputs(target="inbox/not-a-date.md"), vault=vault, apply=False)
    assert not res.ok
    assert res.escalation is not None
    assert res.escalation["step"] == "detect_shape"


def test_escalates_when_under_projects(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "X").mkdir()
    (vault / "projects" / "X" / "2026-05-12.md").write_text("")
    res = file_daily_note(DailyInputs(target="projects/X/2026-05-12.md"), vault=vault, apply=False)
    assert not res.ok
    assert res.escalation is not None
    assert res.escalation["step"] == "inspect_parent"


def test_escalates_on_destination_collision(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("source\n")
    daily = vault / "resources" / "daily_notes" / "2026" / "05"
    daily.mkdir(parents=True)
    (daily / "2026-05-12.md").write_text("existing\n")
    res = file_daily_note(DailyInputs(target="inbox/2026-05-12.md"), vault=vault, apply=False)
    assert not res.ok
    assert res.escalation is not None
    assert res.escalation["step"] == "check_collision"


def test_apply_migrates_backmatter(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    src = vault / "inbox" / "2026-05-12.md"
    src.write_text("# 2026-05-12\n\nbody\n\n---\nfoo: bar\n---\n")
    res = file_daily_note(DailyInputs(target="2026-05-12"), vault=vault, apply=True)
    assert res.ok
    assert res.plan.frontmatter_migrated is True
    dest = vault / "resources" / "daily_notes" / "2026" / "05" / "2026-05-12.md"
    text = dest.read_text()
    assert text.startswith("---\nfoo: bar\n---\n")
    assert text.count("---") == 2


def test_zero_match_escalation(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    res = file_daily_note(DailyInputs(target="2026-05-12"), vault=vault, apply=False)
    assert not res.ok
    assert res.escalation is not None
    assert res.escalation["step"] == "resolve_target"


def test_missing_date_plans_creation_without_mutating_vault(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    before = sorted(path.relative_to(vault) for path in vault.rglob("*"))

    res = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True),
        vault=vault,
        apply=False,
    )

    assert res.ok
    assert res.plan.source is None
    assert res.plan.destination == "resources/daily_notes/2026/09/2026-09-02.md"
    assert res.plan.would_create is True
    assert res.created is False
    assert sorted(path.relative_to(vault) for path in vault.rglob("*")) == before


def test_missing_date_apply_creates_exact_h1_only_note(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)

    res = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True),
        vault=vault,
        apply=True,
    )

    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"
    assert res.ok
    assert res.moved is False
    assert res.created is True
    assert res.plan.would_create is True
    assert destination.read_text(encoding="utf-8") == "# 2026-09-02\n\n"


def test_missing_invalid_date_and_collision_never_write(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    (vault / "areas" / "2026-09-02.md").write_text("collision\n", encoding="utf-8")

    invalid = file_daily_note(
        DailyInputs(target="2026-02-31", create_missing=True),
        vault=vault,
        apply=True,
    )
    collision = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True),
        vault=vault,
        apply=True,
    )

    assert invalid.escalation is not None
    assert invalid.escalation["step"] == "detect_shape"
    assert collision.escalation is not None
    assert collision.escalation["step"] == "check_collision"
    assert not (vault / "resources/daily_notes/2026/02/2026-02-31.md").exists()
    assert not (vault / "resources/daily_notes/2026/09/2026-09-02.md").exists()


def test_missing_arbitrary_path_does_not_enter_authoring(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)

    res = file_daily_note(
        DailyInputs(target="inbox/2026-09-02.md", create_missing=True),
        vault=vault,
        apply=True,
    )

    assert res.escalation is not None
    assert res.escalation["step"] == "resolve_target"
    assert not (vault / "resources/daily_notes/2026/09/2026-09-02.md").exists()


def test_apply_creation_smokes_copied_sample_vault(tmp_path: Path) -> None:
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)

    res = file_daily_note(
        DailyInputs(target="2026-09-02", create_missing=True),
        vault=vault,
        apply=True,
    )

    payload = res.to_dict()
    destination = vault / "resources/daily_notes/2026/09/2026-09-02.md"
    assert payload["ok"] is True
    assert payload["moved"] is False
    assert payload["created"] is True
    assert payload["plan"]["source"] is None
    assert payload["plan"]["would_create"] is True
    assert destination.read_text(encoding="utf-8") == "# 2026-09-02\n\n"
    assert validate_paths(vault, [destination]).issues == []


def test_no_roundup_flag_does_not_scan_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _seed_vault(tmp_path)
    source = vault / "inbox/2026-09-07.md"
    source.write_text("# 2026-09-07\n\n", encoding="utf-8")

    def unexpected_scan(*args, **kwargs):
        raise AssertionError("ordinary pqn-daily scanned the vault for tasks")

    monkeypatch.setattr(
        "para_quest_notes.workflows.daily.steps.compose_task_roundup.scan_vault_tasks",
        unexpected_scan,
    )

    result = file_daily_note(DailyInputs(target="2026-09-07"), vault=vault)

    assert result.ok
    assert result.task_roundup is None
    assert source.read_text(encoding="utf-8") == "# 2026-09-07\n\n"


def test_task_roundup_dry_run_uses_selected_date_without_writing(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    source = vault / "inbox/2026-09-07.md"
    source.write_text("# 2026-09-07\n\nDaily text.\n", encoding="utf-8")
    (vault / "projects/Project.md").write_text(
        "# Project\n\n- [ ] Today 📅 2026-09-07\n",
        encoding="utf-8",
    )

    result = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=False,
    )

    assert result.ok
    assert result.task_roundup is not None
    assert result.task_roundup.reference_date == "2026-09-07"
    assert result.task_roundup.action == "insert"
    assert result.task_roundup.applied is False
    assert result.task_roundup.summary["due_today"] == 1
    assert source.read_text(encoding="utf-8") == "# 2026-09-07\n\nDaily text.\n"
    assert not (vault / "resources/daily_notes/2026/09/2026-09-07.md").exists()


def test_task_roundup_apply_moves_one_composed_note(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    source = vault / "inbox/2026-09-07.md"
    source.write_text("# 2026-09-07\n\nDaily text.\n", encoding="utf-8")
    (vault / "projects/Project.md").write_text(
        "# Project\n\n- [ ] Today 📅 2026-09-07\n",
        encoding="utf-8",
    )

    result = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    destination = vault / "resources/daily_notes/2026/09/2026-09-07.md"
    assert result.ok
    assert result.moved is True
    assert result.task_roundup is not None
    assert result.task_roundup.action == "insert"
    assert result.task_roundup.applied is True
    assert not source.exists()
    assert destination.read_text(encoding="utf-8").startswith(
        "# 2026-09-07\n\nDaily text.\n\n" + START_MARKER
    )
    assert "- [[Project]] Today (due 2026-09-07)" in destination.read_text(encoding="utf-8")


def test_task_roundup_apply_rewrites_canonical_then_is_idempotent(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    destination = vault / "resources/daily_notes/2026/09/2026-09-07.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("# 2026-09-07\n\n", encoding="utf-8")
    (vault / "projects/Project.md").write_text(
        "# Project\n\n- [ ] Today 📅 2026-09-07\n",
        encoding="utf-8",
    )

    first = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )
    first_bytes = destination.read_bytes()
    second = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    assert first.task_roundup is not None
    assert first.task_roundup.action == "insert"
    assert second.task_roundup is not None
    assert second.task_roundup.action == "unchanged"
    assert destination.read_bytes() == first_bytes


def test_task_roundup_insert_preserves_crlf_frontmatter_and_body(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    destination = vault / "resources/daily_notes/2026/09/2026-09-07.md"
    destination.parent.mkdir(parents=True)
    original = b"---\r\ncustom: 'keep quotes'\r\n---\r\n# 2026-09-07\r\n\r\nUser-owned text.\r\n"
    destination.write_bytes(original)

    result = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    assert result.ok
    assert result.task_roundup is not None
    assert result.task_roundup.action == "insert"
    assert destination.read_bytes().startswith(original)


def test_task_roundup_replace_preserves_mixed_newlines_around_region(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    destination = vault / "resources/daily_notes/2026/09/2026-09-07.md"
    destination.parent.mkdir(parents=True)
    prefix = b"# 2026-09-07\r\n\r\nBefore.\n"
    suffix = b"After.\r\n"
    destination.write_bytes(
        prefix + START_MARKER.encode() + b"\r\nstale\r\n" + END_MARKER.encode() + b"\r\n" + suffix
    )

    result = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    assert result.ok
    assert result.task_roundup is not None
    assert result.task_roundup.action == "replace"
    rewritten = destination.read_bytes()
    assert rewritten.startswith(prefix)
    assert rewritten.endswith(suffix)
    assert b"stale" not in rewritten


def test_task_roundup_rejects_concurrent_note_edit_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = _seed_vault(tmp_path)
    destination = vault / "resources/daily_notes/2026/09/2026-09-07.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("# 2026-09-07\n\nOriginal.\n", encoding="utf-8")

    from para_quest_notes.workflows.daily.steps import compose_task_roundup

    real_scan = compose_task_roundup.scan_vault_tasks

    def scan_after_edit(*args, **kwargs):
        destination.write_text("# 2026-09-07\n\nConcurrent edit.\n", encoding="utf-8")
        return real_scan(*args, **kwargs)

    monkeypatch.setattr(compose_task_roundup, "scan_vault_tasks", scan_after_edit)

    result = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "move_file"
    assert destination.read_text(encoding="utf-8") == "# 2026-09-07\n\nConcurrent edit.\n"


def test_task_roundup_in_place_refresh_preserves_file_mode(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    destination = vault / "resources/daily_notes/2026/09/2026-09-07.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("# 2026-09-07\n\n", encoding="utf-8")
    destination.chmod(0o600)

    result = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    assert result.ok
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_task_roundup_composes_with_missing_note_creation(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    (vault / "projects/Project.md").write_text(
        "# Project\n\n- [ ] Today 📅 2026-09-07\n",
        encoding="utf-8",
    )

    result = file_daily_note(
        DailyInputs(
            target="2026-09-07",
            create_missing=True,
            task_roundup=True,
        ),
        vault=vault,
        apply=True,
    )

    destination = vault / "resources/daily_notes/2026/09/2026-09-07.md"
    assert result.ok
    assert result.created is True
    assert result.task_roundup is not None
    assert destination.read_text(encoding="utf-8").startswith("# 2026-09-07\n\n" + START_MARKER)


def test_malformed_roundup_markers_fail_before_move(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    source = vault / "inbox/2026-09-07.md"
    original = f"# 2026-09-07\n\n{START_MARKER}\nbroken\n"
    source.write_text(original, encoding="utf-8")

    result = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "compose_task_roundup"
    assert source.read_text(encoding="utf-8") == original
    assert not (vault / "resources/daily_notes/2026/09/2026-09-07.md").exists()


def test_unclosed_fence_fails_before_move(tmp_path: Path) -> None:
    vault = _seed_vault(tmp_path)
    source = vault / "inbox/2026-09-07.md"
    original = "# 2026-09-07\n\n```markdown\nunclosed example\n"
    source.write_text(original, encoding="utf-8")

    result = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "compose_task_roundup"
    assert source.read_text(encoding="utf-8") == original
    assert not (vault / "resources/daily_notes/2026/09/2026-09-07.md").exists()


def test_task_roundup_apply_smokes_copied_sample_vault(tmp_path: Path) -> None:
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)
    destination = vault / "resources/daily_notes/2026/09/2026-09-07.md"

    dry_run = file_daily_note(
        DailyInputs(
            target="2026-09-07",
            create_missing=True,
            task_roundup=True,
        ),
        vault=vault,
        apply=False,
    )
    applied = file_daily_note(
        DailyInputs(
            target="2026-09-07",
            create_missing=True,
            task_roundup=True,
        ),
        vault=vault,
        apply=True,
    )
    first_bytes = destination.read_bytes()
    rerun = file_daily_note(
        DailyInputs(target="2026-09-07", task_roundup=True),
        vault=vault,
        apply=True,
    )

    assert dry_run.ok
    assert dry_run.task_roundup is not None
    assert dry_run.task_roundup.applied is False
    assert applied.ok and applied.created
    assert applied.task_roundup is not None
    assert rerun.task_roundup is not None
    assert rerun.task_roundup.action == "unchanged"
    assert destination.read_bytes() == first_bytes
    assert destination.read_text(encoding="utf-8").count(START_MARKER) == 1
    assert destination.read_text(encoding="utf-8").count(END_MARKER) == 1
    assert validate_paths(vault, [destination]).issues == []
