"""Tests for adapter.prompts."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.adapter.errors import ConfigError
from para_quest_notes.adapter.prompts import PromptLoader


def test_render_substitutes_vars(tmp_path: Path) -> None:
    (tmp_path / "greet.txt").write_text("hello $name")
    p = PromptLoader(tmp_path).get("greet")
    assert p.render(name="world") == "hello world"


def test_render_missing_var_raises(tmp_path: Path) -> None:
    (tmp_path / "g.txt").write_text("hello $name")
    p = PromptLoader(tmp_path).get("g")
    with pytest.raises(KeyError):
        p.render()


def test_id_is_stable_for_same_text(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("same body")
    (tmp_path / "b.txt").write_text("same body")
    a = PromptLoader(tmp_path).get("a")
    b = PromptLoader(tmp_path).get("b")
    # Different names → different ids; hash suffix should match.
    assert a.id != b.id
    assert a.id.split("@")[1] == b.id.split("@")[1]


def test_id_changes_when_text_changes(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("v1")
    a1 = PromptLoader(tmp_path).get("a")
    (tmp_path / "a.txt").write_text("v2")
    a2 = PromptLoader(tmp_path).get("a")
    assert a1.id != a2.id


def test_missing_prompt_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        PromptLoader(tmp_path).get("missing")


def test_available_lists_prompts(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "ignore.md").write_text("")
    assert PromptLoader(tmp_path).available() == ["a", "b"]


def test_available_handles_missing_dir(tmp_path: Path) -> None:
    assert PromptLoader(tmp_path / "nope").available() == []
