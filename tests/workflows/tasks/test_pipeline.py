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


def test_scheduled_parsed_but_not_required(tmp_path: Path):
    v = tmp_path / "v"
    _write(v / "projects" / "P.md", "# P\n- [ ] only scheduled ⏳ 2026-07-18\n")
    report = scan_vault_tasks(v, today=TODAY, due_in=7)
    # No due date -> not reported.
    assert report.tasks == []


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


def test_sorted_by_due_date(tmp_path: Path):
    report = scan_vault_tasks(_vault(tmp_path), today=TODAY, due_in=3650)
    dues = [t.due for t in report.tasks]
    assert dues == sorted(dues)
