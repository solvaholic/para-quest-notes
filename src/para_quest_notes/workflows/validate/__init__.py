"""``pqn-validate`` — vault integrity checks (no LLM).

Audits a vault for issues that quietly break wikilinks or note metadata:

* duplicate filenames across directories (ambiguous ``[[wikilinks]]``)
* invalid YAML frontmatter (the top ``---...---`` block)
* invalid YAML backmatter (the optional bottom ``---...---`` block)

Mirrors the scope of the legacy ``validate-note-integrity`` SKILL. By
design this workflow does **not** validate wikilink targets, orphan
detection, or PARA placement — those are out of scope until a concrete
need surfaces.
"""
