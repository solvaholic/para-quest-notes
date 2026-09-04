"""Tests for the pqn-tasks scanning pipeline."""

from __future__ import annotations

import shutil
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
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n# Health\n",
    )
    _write(
        v / "areas" / "Maintain Home.md",
        "---\ntype: area\nquest-kind: side\nsupports:\n- '[[Health]]'\n---\n# Maintain Home\n",
    )
    _write(
        v / "projects" / "Garden.md",
        "---\ntype: project\nquest-kind: none\nsupports:\n- '[[Maintain Home]]'\n---\n"
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


def test_type_filter_is_repeatable_include_only_and_drops_untyped(tmp_path: Path):
    v = tmp_path / "v"
    _write(v / "projects" / "P.md", "# P\n- [ ] Project task 📅 2026-07-01\n")
    _write(v / "areas" / "A.md", "# A\n- [ ] Area task 📅 2026-07-01\n")
    _write(v / "resources" / "R.md", "# R\n- [ ] Resource task 📅 2026-07-01\n")
    _write(v / "inbox" / "I.md", "# I\n- [ ] Untyped task 📅 2026-07-01\n")

    report = scan_vault_tasks(v, today=TODAY, types=["project", "area"])

    assert {task.description for task in report.tasks} == {"Project task", "Area task"}
    assert report.types == ["area", "project"]


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


def test_untracked_task_excluded_by_default(tmp_path: Path):
    v = tmp_path / "v"
    _write(v / "projects" / "P.md", "# P\n- [ ] no dates at all\n")
    assert scan_vault_tasks(v, today=TODAY, due_in=7).tasks == []


def test_unscheduled_show_uses_active_date_fields_and_preserves_raw_dates(tmp_path: Path):
    v = tmp_path / "v"
    _write(
        v / "projects" / "P.md",
        "# P\n"
        "- [ ] scheduled task ⏳ 2026-07-18\n"
        "- [ ] due still needs scheduling 📅 2026-07-20\n"
        "- [ ] truly undated\n",
    )

    report = scan_vault_tasks(
        v,
        today=TODAY,
        due_in=7,
        date_fields=["scheduled"],
        unscheduled="show",
    )

    by_description = {task.description: task for task in report.tasks}
    assert by_description["scheduled task"].bucket == "upcoming"
    due_only = by_description["due still needs scheduling"]
    assert due_only.bucket == "unscheduled"
    assert due_only.effective_date is None
    assert due_only.date_source is None
    assert due_only.due == "2026-07-20"
    assert by_description["truly undated"].bucket == "unscheduled"
    assert report.to_dict()["summary"] == {
        "total": 3,
        "overdue": 0,
        "due_today": 0,
        "upcoming": 1,
        "unscheduled": 2,
    }


def test_unscheduled_only_excludes_every_task_with_an_active_date(tmp_path: Path):
    v = tmp_path / "v"
    _write(
        v / "projects" / "P.md",
        "# P\n- [ ] past 📅 2026-07-01\n- [ ] beyond horizon 📅 2027-07-01\n- [ ] no date\n",
    )

    report = scan_vault_tasks(v, today=TODAY, due_in=0, unscheduled="only")

    assert [task.description for task in report.tasks] == ["no date"]
    assert report.tasks[0].bucket == "unscheduled"


def test_overdue_show_includes_overdue_and_unscheduled(tmp_path: Path):
    v = tmp_path / "v"
    _write(
        v / "projects" / "P.md",
        "# P\n- [ ] old 📅 2026-07-01\n- [ ] today 📅 2026-07-17\n- [ ] no date\n",
    )

    report = scan_vault_tasks(
        v,
        today=TODAY,
        overdue_only=True,
        unscheduled="show",
    )

    assert [(task.description, task.bucket) for task in report.tasks] == [
        ("old", "overdue"),
        ("no date", "unscheduled"),
    ]


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


def test_unscheduled_sort_after_dated_by_path_and_line(tmp_path: Path):
    v = tmp_path / "v"
    _write(v / "projects" / "B.md", "# B\n- [ ] B second\n- [ ] B third\n")
    _write(v / "projects" / "A.md", "# A\n- [ ] A undated\n- [ ] A dated 📅 2026-07-17\n")

    report = scan_vault_tasks(v, today=TODAY, unscheduled="show")

    assert [task.description for task in report.tasks] == [
        "A dated",
        "A undated",
        "B second",
        "B third",
    ]


def test_unscheduled_only_smokes_copied_sample_vault(tmp_path: Path):
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)

    report = scan_vault_tasks(vault, today=TODAY, unscheduled="only")

    assert len(report.tasks) == 34
    assert report.to_dict()["summary"] == {
        "total": 34,
        "overdue": 0,
        "due_today": 0,
        "upcoming": 0,
        "unscheduled": 34,
    }
    assert all(task.bucket == "unscheduled" for task in report.tasks)
    assert all(task.effective_date is None and task.date_source is None for task in report.tasks)
    assert [(task.path, task.line) for task in report.tasks] == sorted(
        (task.path, task.line) for task in report.tasks
    )
