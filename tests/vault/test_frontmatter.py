"""Tests for the ingest_inbox frontmatter parser/serializer."""

from __future__ import annotations

from para_quest_notes.vault.frontmatter import (
    canonical_frontmatter,
    dump_frontmatter,
    merge,
    migrate_quest_kind,
    parse,
    read_quest_kind,
    split_note,
)


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


# ---------------------------------------------------------------------------
# canonical_frontmatter / dump_frontmatter
# ---------------------------------------------------------------------------


def test_canonical_orders_known_keys_first():
    out = canonical_frontmatter(
        {
            "supports": ["[[Health]]"],
            "created": "2026-05-12",
            "quest-kind": "none",
            "type": "project",
        }
    )
    assert list(out.keys()) == ["type", "quest-kind", "supports", "created"]


def test_canonical_appends_unknown_keys_in_input_order():
    out = canonical_frontmatter(
        {"capability": True, "type": "area", "tags": ["x"], "quest-kind": "none"}
    )
    # Known keys (type, quest-kind) lead; then unknown keys in input order.
    assert list(out.keys()) == ["type", "quest-kind", "capability", "tags"]


def test_canonical_drops_none_values():
    out = canonical_frontmatter({"type": "resource", "quest-kind": "none", "source_url": None})
    assert "source_url" not in out
    assert out == {"type": "resource", "quest-kind": "none"}


def test_canonical_drops_empty_supports():
    out = canonical_frontmatter({"type": "area", "quest": "none", "supports": []})
    assert "supports" not in out
    out2 = canonical_frontmatter({"type": "area", "quest": "none", "supports": None})
    assert "supports" not in out2


def test_canonical_keeps_non_empty_supports():
    out = canonical_frontmatter({"type": "project", "quest": "none", "supports": ["[[Health]]"]})
    assert out["supports"] == ["[[Health]]"]


def test_dump_frontmatter_quotes_wikilinks():
    text = dump_frontmatter(
        {"type": "project", "quest-kind": "none", "supports": ["[[Health]]", "[[Maintain Home]]"]}
    )
    # Round-trip: parsed back, supports stays as wikilink strings.
    parsed = parse(text + "body\n")
    assert parsed.frontmatter["supports"] == ["[[Health]]", "[[Maintain Home]]"]
    # Sanity: emitted with the expected key order and a trailing newline.
    assert text.startswith("---\ntype: project\nquest-kind: none\nsupports:\n")
    assert text.endswith("---\n")


def test_dump_frontmatter_empty_returns_empty_string():
    assert dump_frontmatter({}) == ""
    # All-None input is also empty.
    assert dump_frontmatter({"type": None, "quest": None}) == ""


def test_dump_frontmatter_omits_empty_supports():
    text = dump_frontmatter({"type": "resource", "quest-kind": "none", "supports": []})
    assert "supports" not in text


# ---------------------------------------------------------------------------
# quest-kind rename: read tolerance + migrate-on-touch (issue #98)
# ---------------------------------------------------------------------------


def test_read_quest_kind_prefers_canonical_key():
    value, used_legacy = read_quest_kind({"quest-kind": "main", "quest": "side"})
    assert value == "main"
    assert used_legacy is False


def test_read_quest_kind_falls_back_to_legacy():
    value, used_legacy = read_quest_kind({"quest": "side"})
    assert value == "side"
    assert used_legacy is True


def test_read_quest_kind_absent():
    assert read_quest_kind({"type": "area"}) == (None, False)


def test_migrate_quest_kind_renames_legacy_in_place():
    out, had_legacy = migrate_quest_kind({"type": "area", "quest": "main", "created": "x"})
    assert had_legacy is True
    assert list(out.keys()) == ["type", "quest-kind", "created"]
    assert out["quest-kind"] == "main"


def test_migrate_quest_kind_canonical_wins_when_both_present():
    out, had_legacy = migrate_quest_kind({"quest": "side", "quest-kind": "main"})
    assert had_legacy is True
    assert out == {"quest-kind": "main"}


def test_migrate_quest_kind_noop_without_legacy():
    data = {"type": "area", "quest-kind": "none"}
    out, had_legacy = migrate_quest_kind(data)
    assert had_legacy is False
    assert out == data


def test_canonical_frontmatter_migrates_legacy_quest_on_touch():
    out = canonical_frontmatter({"type": "project", "quest": "none", "supports": ["[[Health]]"]})
    assert "quest" not in out
    assert out["quest-kind"] == "none"
    assert list(out.keys()) == ["type", "quest-kind", "supports"]


def test_split_note_frontmatter_only():
    text = "---\ntype: project\n---\nbody\n"
    s = split_note(text)
    assert s.had_frontmatter is True
    assert s.had_backmatter is False
    assert s.frontmatter == {"type": "project"}
    assert s.body == "body\n"


def test_split_note_tail_backmatter():
    text = "# X\n\nbody\n\n---\ntype: project\nquest: none\n---\n"
    s = split_note(text)
    assert s.had_frontmatter is False
    assert s.had_backmatter is True
    assert s.backmatter == {"type": "project", "quest": "none"}
    assert s.body.rstrip("\n") == "# X\n\nbody"


def test_split_note_front_and_back():
    text = "---\ntype: project\n---\nmiddle\n\n---\nquest: none\n---\n"
    s = split_note(text)
    assert s.frontmatter == {"type": "project"}
    assert s.backmatter == {"quest": "none"}
    assert "middle" in s.body


def test_split_note_no_fences_at_all():
    text = "just a body\n"
    s = split_note(text)
    assert not s.had_frontmatter
    assert not s.had_backmatter


def test_split_note_malformed_backmatter_left_alone():
    text = "body\n\n---\n: not valid yaml :::\n---\n"
    s = split_note(text)
    assert not s.had_backmatter
