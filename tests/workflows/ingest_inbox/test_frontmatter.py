"""Tests for the ingest_inbox frontmatter parser/serializer."""

from __future__ import annotations

from para_quest_notes.workflows.ingest_inbox.frontmatter import merge, parse


def test_parse_no_frontmatter():
    p = parse("# hello\n\nbody")
    assert p.had_frontmatter is False
    assert p.frontmatter == {}
    assert p.body == "# hello\n\nbody"


def test_parse_with_frontmatter():
    text = "---\ntype: project\nquest: none\n---\n# hello\n"
    p = parse(text)
    assert p.had_frontmatter is True
    assert p.frontmatter == {"type": "project", "quest": "none"}
    assert p.body == "# hello\n"


def test_parse_malformed_yaml_treats_as_body():
    text = "---\n: : :\n---\nfoo"
    p = parse(text)
    assert p.had_frontmatter is False
    assert p.body == text


def test_parse_no_closing_delim_treats_as_body():
    text = "---\ntype: project\nfoo bar\n"
    p = parse(text)
    assert p.had_frontmatter is False
    assert p.body == text


def test_render_round_trips():
    text = "---\ntype: project\nsupports:\n- '[[Health]]'\n---\nbody\n"
    p = parse(text)
    out = parse(p.render())
    assert out.frontmatter == p.frontmatter
    assert out.body == p.body


def test_render_no_frontmatter():
    p = parse("just a body")
    assert p.render() == "just a body"


def test_merge_preserves_order_and_overrides():
    existing = {"type": "area", "quest": "none", "extra": 1}
    out = merge(existing, {"quest": "main", "supports": ["[[Health]]"]})
    assert list(out.keys()) == ["type", "quest", "extra", "supports"]
    assert out["quest"] == "main"
    assert out["supports"] == ["[[Health]]"]
