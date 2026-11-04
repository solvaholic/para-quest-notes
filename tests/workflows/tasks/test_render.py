"""Tests for reusable ``pqn-tasks`` markdown rendering."""

from __future__ import annotations

from para_quest_notes.workflows.tasks.contract import TaskItem, TasksReport
from para_quest_notes.workflows.tasks.render import render_markdown


def _report() -> TasksReport:
    return TasksReport(
        vault="/vault",
        reference_date="2026-09-07",
        due_in=7,
        group_by="due",
        date_fields=["due", "scheduled", "start"],
        include_archive=False,
        types=None,
        quest=None,
        files_scanned=3,
        tasks=[
            TaskItem(
                path="projects/Build Raised Beds.md",
                line=12,
                description="Order soil",
                raw="Order soil 📅 2026-09-06",
                state=" ",
                bucket="overdue",
                effective_date="2026-09-06",
                date_source="due",
                due="2026-09-06",
            ),
            TaskItem(
                path="areas/Garden.md",
                line=8,
                description="Call supplier",
                raw="Call supplier ⏳ 2026-09-07",
                state="/",
                bucket="due_today",
                effective_date="2026-09-07",
                date_source="scheduled",
                scheduled="2026-09-07",
            ),
        ],
    )


def test_default_render_preserves_standalone_markdown() -> None:
    assert render_markdown(_report()) == (
        "# Tasks as of 2026-09-07 (within 7 day(s))\n"
        "\n"
        "## Overdue (1)\n"
        "- [[Build Raised Beds]] Order soil (due 2026-09-06)\n"
        "\n"
        "## Due today (1)\n"
        "- [[Garden]] Call supplier (scheduled 2026-09-07)\n"
    )


def test_embedded_render_demotes_headings_without_live_checkboxes() -> None:
    rendered = render_markdown(_report(), heading_level=2)

    assert rendered.startswith("## Tasks as of 2026-09-07 (within 7 day(s))\n")
    assert "\n### Overdue (1)\n" in rendered
    assert "\n### Due today (1)\n" in rendered
    assert "- [ ]" not in rendered


def test_empty_embedded_render_keeps_existing_empty_state() -> None:
    report = _report()
    report.tasks = []

    assert render_markdown(report, heading_level=2) == (
        "## Tasks as of 2026-09-07 (within 7 day(s))\n\nNo open tasks due.\n"
    )
