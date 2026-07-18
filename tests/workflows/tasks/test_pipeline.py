"""Tests for the pqn-tasks scanning pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from para_quest_notes.workflows.tasks.pipeline import scan_vault_tasks

TODAY = date(2026, 7, 17)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    _write(
        v / "areas" / "Health.md",
        "---\ntype: area\nquest: main\nsupports:\n- '[[Health]]'\n---\n# Health\n",
    )
    _write(
        v / "areas" / "Maintain Home.md",
        "---\ntype: area\nquest: side\nsupports:\n- '[[Health]]'\n---\n# Maintain Home\n",
    )
    _write(
        v / "projects" / "Garden.md",
        "---\ntype: project\nquest: none\nsupports:\n- '[[Maintain Home]]'\n---\n"
        "# Garden\n\n## Tasks\n\n"
        "- [ ] Overdue 📅 2026-07-01\n"
        "- [ ] Today 📅 2026-07-17\n"
        "- [ ] Soon 📅 2026-07-19\n"
        "- [ ] Far 📅 2026-12-31\n"
        "- [ ] No date here\n"
        "- [x] Done 📅 2026-07-01\n",
    )
    _write(v / "inbox" / "capture.md", "# capture\n- [ ] Buy milk 📅 2026-07-02\n")
    return v


def test_buckets_within_default_horizon(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=7)
    descs = {(t.description, t.bucket) for t in report.tasks}
    assert ("Overdue", "overdue") in descs
    assert ("Today", "due_today") in descs
    assert ("Soon", "upcoming") in descs
    assert ("Buy milk", "overdue") in descs
    # "Far" is beyond the 7-day horizon; "No date" and "Done" are excluded.
    assert all(t.description not in {"Far", "No date here", "Done"} for t in report.tasks)


def test_due_in_widens_horizon(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=3650)
    assert any(t.description == "Far" for t in report.tasks)


def test_overdue_only(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=7, overdue_only=True)
    assert {t.bucket for t in report.tasks} == {"overdue"}
    assert {t.description for t in report.tasks} == {"Overdue", "Buy milk"}


def test_quest_rollup_and_area_keys(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=7)
    garden = next(t for t in report.tasks if t.description == "Overdue")
    assert garden.areas == ["Maintain Home"]
    assert garden.quests == ["Health"]  # side quest rolled up to its main


def test_unassigned_when_no_supports(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=7)
    milk = next(t for t in report.tasks if t.description == "Buy milk")
    assert milk.supports == []
    assert milk.areas == []
    assert milk.quests == []


def test_quest_filter(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=7, quest="[[Maintain Home]]")
    assert report.tasks  # Garden supports Maintain Home
    assert all(t.path.startswith("projects/") for t in report.tasks)


def test_quest_filter_is_case_insensitive(tmp_path: Path):
    # Parity with pqn-quests: --quest matches case-insensitively and
    # tolerates a bare name (no wikilink).
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=7, quest="maintain home")
    assert report.tasks
    assert all(t.path.startswith("projects/") for t in report.tasks)


def test_scheduled_only_is_reported(tmp_path: Path):
    # A task with only a scheduled ("do") date must be reported — the
    # effective-date resolution falls through to it. No config needed.
    v = tmp_path / "v"
    _write(v / "projects" / "P.md", "# P\n- [ ] only scheduled ⏳ 2026-07-18\n")
    report = scan_vault_tasks(v, today=TODAY, due_in=7)
    (task,) = report.tasks
    assert task.effective_date == "2026-07-18"
    assert task.date_source == "scheduled"
    assert task.bucket == "upcoming"


def test_start_only_is_reported(tmp_path: Path):
    v = tmp_path / "v"
    _write(v / "projects" / "P.md", "# P\n- [ ] start only 🛫 2026-07-01\n")
    (task,) = scan_vault_tasks(v, today=TODAY, due_in=7).tasks
    assert task.date_source == "start"
    assert task.bucket == "overdue"


def test_untracked_task_excluded(tmp_path: Path):
    v = tmp_path / "v"
    _write(v / "projects" / "P.md", "# P\n- [ ] no dates at all\n")
    assert scan_vault_tasks(v, today=TODAY, due_in=7).tasks == []


def test_default_precedence_prefers_due(tmp_path: Path):
    v = tmp_path / "v"
    _write(
        v / "projects" / "P.md",
        "# P\n- [ ] multi ⏳ 2026-07-16 📅 2026-07-01 🛫 2026-07-10\n",
    )
    (task,) = scan_vault_tasks(v, today=TODAY, due_in=7).tasks
    assert task.date_source == "due"
    assert task.effective_date == "2026-07-01"
    assert task.bucket == "overdue"
    # All three raw dates are still surfaced.
    assert task.due == "2026-07-01"
    assert task.scheduled == "2026-07-16"
    assert task.start == "2026-07-10"


def test_date_fields_reorders_precedence(tmp_path: Path):
    v = tmp_path / "v"
    _write(
        v / "projects" / "P.md",
        "# P\n- [ ] multi ⏳ 2026-07-16 📅 2026-07-01\n",
    )
    (task,) = scan_vault_tasks(v, today=TODAY, due_in=7, date_fields=["scheduled", "due"]).tasks
    assert task.date_source == "scheduled"
    assert task.effective_date == "2026-07-16"


def test_date_fields_filters_out_omitted(tmp_path: Path):
    # date_fields=["scheduled"] ignores due-only tasks entirely.
    v = tmp_path / "v"
    _write(v / "projects" / "D.md", "# D\n- [ ] due only 📅 2026-07-17\n")
    _write(v / "projects" / "S.md", "# S\n- [ ] sched only ⏳ 2026-07-17\n")
    report = scan_vault_tasks(v, today=TODAY, due_in=7, date_fields=["scheduled"])
    assert {t.path for t in report.tasks} == {"projects/S.md"}
    assert report.date_fields == ["scheduled"]


def test_archive_excluded_by_default(tmp_path: Path):
    v = tmp_path / "v"
    _write(v / "archive" / "old.md", "# old\n- [ ] Ancient 📅 2026-07-01\n")
    _write(v / "projects" / "cur.md", "# cur\n- [ ] Fresh 📅 2026-07-01\n")
    default = scan_vault_tasks(v, today=TODAY, due_in=7)
    assert {t.description for t in default.tasks} == {"Fresh"}
    included = scan_vault_tasks(v, today=TODAY, due_in=7, include_archive=True)
    assert {t.description for t in included.tasks} == {"Fresh", "Ancient"}


def test_file_line_numbers_account_for_frontmatter(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=7)
    overdue = next(t for t in report.tasks if t.description == "Overdue")
    # frontmatter (6 lines) + "# Garden"(7) + ""(8) + "## Tasks"(9) + ""(10) + task(11)
    assert overdue.line == 11


def test_sorted_by_effective_date(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=3650)
    dates = [t.effective_date for t in report.tasks]
    assert dates == sorted(dates)
