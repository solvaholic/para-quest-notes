"""Tests for the YAML block extractor used by ``pqn-validate``."""

from __future__ import annotations

from para_quest_notes.workflows.validate._blocks import extract_blocks


def test_no_frontmatter_no_backmatter():
    blocks = extract_blocks("just a body\nwith two lines\n")
    assert blocks.frontmatter is None
    assert blocks.backmatter is None
    assert not blocks.frontmatter_unterminated


def test_frontmatter_only():
    text = "---\ntitle: hi\ntags: [a, b]\n---\nbody here\n"
    blocks = extract_blocks(text)
    assert blocks.frontmatter is not None
    assert blocks.frontmatter.start_line == 1
    assert blocks.frontmatter.end_line == 4
    assert "title: hi" in blocks.frontmatter.text
    assert blocks.backmatter is None


def test_frontmatter_unterminated():
    text = "---\ntitle: hi\nbody no closer\n"
    blocks = extract_blocks(text)
    assert blocks.frontmatter is None
    assert blocks.frontmatter_unterminated


def test_backmatter_only():
    text = "body line\n---\noutcome: shipped\n---\n"
    blocks = extract_blocks(text)
    assert blocks.frontmatter is None
    assert blocks.backmatter is not None
    assert "outcome: shipped" in blocks.backmatter.text
    # 1-based: opener is line 2, closer is line 4.
    assert blocks.backmatter.start_line == 2
    assert blocks.backmatter.end_line == 4


def test_frontmatter_and_backmatter():
    text = "---\nkind: project\n---\ndid stuff\n---\noutcome: done\n---\n"
    blocks = extract_blocks(text)
    assert blocks.frontmatter is not None
    assert blocks.backmatter is not None
    assert "kind: project" in blocks.frontmatter.text
    assert "outcome: done" in blocks.backmatter.text


def test_horizontal_rule_in_body_is_not_a_fence():
    # Single `---` in body, not paired — must not be misread as backmatter.
    text = "---\nkind: note\n---\nfirst para\n\n---\n\nsecond para\n"
    blocks = extract_blocks(text)
    assert blocks.frontmatter is not None
    # The trailing `---` is not the last non-blank line, so no backmatter.
    assert blocks.backmatter is None


def test_empty_file():
    blocks = extract_blocks("")
    assert blocks.frontmatter is None
    assert blocks.backmatter is None


def test_adjacent_fences_not_backmatter():
    # `---\n---` at end of file is not a real block.
    text = "body\n---\n---\n"
    blocks = extract_blocks(text)
    assert blocks.backmatter is None
