"""Tests for the shared fence-aware task scanner."""

from __future__ import annotations

from datetime import date

from para_quest_notes.vault.tasks import (
    OPEN_STATES,
    TASKS_META_EMOJI,
    scan_tasks,
)


def test_scans_all_states_with_line_numbers():
    body = "intro\n- [ ] one\n- [/] two\n- [x] done\n- [-] cancelled\n"
    tasks = scan_tasks(body)
    assert [t.line for t in tasks] == [2, 3, 4, 5]
    assert [t.state for t in tasks] == [" ", "/", "x", "-"]
    assert [t.is_open for t in tasks] == [True, True, False, False]


def test_open_states_constant():
    assert OPEN_STATES == (" ", "/")


def test_skips_backtick_fenced_block():
    body = "```\n- [ ] not a task\n```\n- [ ] real\n"
    tasks = scan_tasks(body)
    assert len(tasks) == 1
    assert tasks[0].line == 4


def test_skips_tilde_fenced_block():
    body = "~~~\n- [ ] not a task\n~~~\n- [ ] real\n"
    tasks = scan_tasks(body)
    assert len(tasks) == 1


def test_longer_fence_not_closed_by_shorter_run():
    # A 4-backtick fence is not closed by a 3-backtick line (CommonMark).
    body = "````\n```\n- [ ] hidden 📅 2026-07-17\n````\n- [ ] real\n"
    tasks = scan_tasks(body)
    assert [t.description for t in tasks] == ["real"]


def test_info_string_on_opening_fence():
    body = "```python\n- [ ] not a task\n```\n- [ ] real\n"
    tasks = scan_tasks(body)
    assert len(tasks) == 1


def test_parses_emoji_dates():
    body = "- [ ] pay taxes 📅 2026-07-10 ⏳ 2026-07-05 🛫 2026-07-01\n"
    (task,) = scan_tasks(body)
    assert task.due == date(2026, 7, 10)
    assert task.scheduled == date(2026, 7, 5)
    assert task.start == date(2026, 7, 1)


def test_missing_dates_are_none():
    (task,) = scan_tasks("- [ ] no dates here\n")
    assert task.due is None and task.scheduled is None and task.start is None


def test_invalid_date_is_ignored():
    # 2026-13-40 is not a real date; parsing must not raise.
    (task,) = scan_tasks("- [ ] weird 📅 2026-13-40\n")
    assert task.due is None


def test_extra_trailing_digit_rejects_date():
    # A typo'd date must not match its valid ISO prefix.
    (task,) = scan_tasks("- [ ] typo 📅 2026-07-170\n")
    assert task.due is None


def test_description_strips_metadata_and_block_id():
    (task,) = scan_tasks("- [ ] Pay taxes 📅 2026-07-10 ^abc-1\n")
    assert task.description == "Pay taxes"
    assert task.block_id == "abc-1"
    assert task.text.strip().endswith("^abc-1")


def test_description_without_metadata():
    (task,) = scan_tasks("- [ ] Just a plain task\n")
    assert task.description == "Just a plain task"


def test_meta_emoji_membership():
    assert "📅" in TASKS_META_EMOJI
    assert "⏳" in TASKS_META_EMOJI
    assert "🛫" in TASKS_META_EMOJI
