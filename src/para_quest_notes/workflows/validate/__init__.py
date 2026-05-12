"""``pqn-validate`` — vault integrity checks (no LLM).

Audits a vault for issues that quietly break wikilinks or note metadata:

* duplicate filenames across directories (ambiguous ``[[wikilinks]]``)
* invalid YAML frontmatter (the top ``---...---`` block)
* invalid YAML backmatter (the optional bottom ``---...---`` block)

Out of scope today: wikilink target validation, orphan detection,
attachment-reference checks, and PARA placement (the structural
``type:`` vs directory check is a known follow-up).
"""
