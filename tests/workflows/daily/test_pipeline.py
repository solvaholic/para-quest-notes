"""End-to-end pipeline tests for ``pqn-daily``."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.workflows.daily.contract import DailyInputs
from para_quest_notes.workflows.daily.pipeline import file_daily_note


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
