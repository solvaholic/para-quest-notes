"""Tests for adapter.trace."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from para_quest_notes.adapter.trace import TraceWriter, default_state_dir, new_run_path


def test_writes_one_json_per_line(tmp_path: Path) -> None:
    p = tmp_path / "run.jsonl"
    with TraceWriter(p) as w:
        w.write({"event": "a", "n": 1})
        w.write({"event": "b", "n": 2})
    lines = p.read_text().strip().split("\n")
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["event"] == "a"
    assert parsed[1]["n"] == 2
    assert all("ts" in r for r in parsed)


def test_creates_parent_dirs(tmp_path: Path) -> None:
    p = tmp_path / "deep" / "deeper" / "run.jsonl"
    with TraceWriter(p) as w:
        w.write({"event": "x"})
    assert p.exists()


def test_appends_existing_file(tmp_path: Path) -> None:
    p = tmp_path / "run.jsonl"
    with TraceWriter(p) as w:
        w.write({"event": "a"})
    with TraceWriter(p) as w:
        w.write({"event": "b"})
    assert len(p.read_text().strip().split("\n")) == 2


def test_default_state_dir_honors_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert default_state_dir() == tmp_path / "para-quest-notes"


def test_default_state_dir_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    p = default_state_dir()
    assert p.parts[-1] == "para-quest-notes"
    assert ".local" in p.parts and "state" in p.parts


def test_new_run_path_creates_runs_dir(tmp_path: Path) -> None:
    p = new_run_path(tmp_path)
    assert p.parent == tmp_path / "runs"
    assert p.parent.is_dir()
    assert p.suffix == ".jsonl"


def test_serializes_path_objects(tmp_path: Path) -> None:
    p = tmp_path / "run.jsonl"
    with TraceWriter(p) as w:
        w.write({"event": "x", "path": tmp_path / "note.md"})
    record = json.loads(p.read_text().strip())
    assert isinstance(record["path"], str)
