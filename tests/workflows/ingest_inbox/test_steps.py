"""Tests for individual ingest steps with FakeLLM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.fake_llm import FakeLLM
from para_quest_notes.adapter.prompts import Prompt
from para_quest_notes.adapter.step import StepContext
from para_quest_notes.vault.quests import Quest
from para_quest_notes.workflows.ingest_inbox.steps.apply_move import ApplyMove
from para_quest_notes.workflows.ingest_inbox.steps.classify_para import ClassifyPara
from para_quest_notes.workflows.ingest_inbox.steps.pick_quest import PickQuest
from para_quest_notes.workflows.ingest_inbox.steps.plan_destination import PlanDestination
from para_quest_notes.workflows.ingest_inbox.steps.propose_filename import ProposeFilename
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanNote


def _ctx(vault: Path, llm: FakeLLM | None = None) -> StepContext:
    return StepContext(workflow="t", run_id="rid", vault=vault, llm=llm)


def _make_vault(tmp_path: Path) -> Path:
    (tmp_path / "inbox").mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "areas").mkdir()
    (tmp_path / "resources").mkdir()
    (tmp_path / "archive/projects").mkdir(parents=True)
    return tmp_path


# ---- scan_note ----------------------------------------------------------


def test_scan_note_picks_up_attachments(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\nbody\n")
    (vault / "inbox/Foo attachment.txt").write_text("att")
    (vault / "inbox/Other.md").write_text("not mine")

    ctx = _ctx(vault)
    result = ScanNote(source=src).run(ctx)

    scan = ctx.scratchpad["scan"]
    assert scan.title == "Foo"
    assert [p.name for p in scan.attachments] == ["Foo attachment.txt"]
    assert result.meta["had_frontmatter"] is False


def test_scan_note_uses_frontmatter_title(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("---\ntitle: Real Title\n---\nbody")
    ctx = _ctx(vault)
    ScanNote(source=src).run(ctx)
    assert ctx.scratchpad["scan"].title == "Real Title"


# ---- classify_para ------------------------------------------------------


def _para_prompt() -> Prompt:
    return Prompt(name="classify_para", text="t=$title b=$body")


def test_classify_para_happy_path(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\nplan a thing")
    llm = FakeLLM()
    llm.queue(json.dumps({"type": "project", "confidence": 0.9, "reason": "tasks"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    out = ClassifyPara(prompt=_para_prompt()).run(ctx)
    assert out.output["type"] == "project"
    assert ctx.scratchpad["para_type"] == "project"


def test_classify_para_low_confidence_escalates(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"type": "project", "confidence": 0.2, "reason": "meh"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    with pytest.raises(EscalateToUser) as exc:
        ClassifyPara(prompt=_para_prompt()).run(ctx)
    assert exc.value.step == "classify_para"


def test_classify_para_invalid_type_escalates(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"type": "wat", "confidence": 0.9}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    with pytest.raises(EscalateToUser):
        ClassifyPara(prompt=_para_prompt()).run(ctx)


def test_classify_para_empty_response_escalates(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\n")
    llm = FakeLLM()
    llm.queue("")
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    with pytest.raises(EscalateToUser) as exc:
        ClassifyPara(prompt=_para_prompt()).run(ctx)
    assert "empty" in exc.value.reason


# ---- pick_quest ---------------------------------------------------------


def _quest_prompt() -> Prompt:
    return Prompt(
        name="pick_quest",
        text="$title $body $para_type $quest_catalog",
    )


def _quests() -> list[Quest]:
    return [
        Quest(name="Health", quest_kind="main"),
        Quest(name="Connect", quest_kind="main"),
    ]


def test_pick_quest_skipped_for_resource(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\n")
    ctx = _ctx(vault)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "resource"
    ctx.scratchpad["vault_quests"] = _quests()
    out = PickQuest(prompt=_quest_prompt()).run(ctx)
    assert out.output["skipped"] is True
    assert ctx.scratchpad["quests"] == []


def test_pick_quest_happy_path(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"quests": ["Health"], "confidence": 0.9, "reason": "fits"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["vault_quests"] = _quests()
    out = PickQuest(prompt=_quest_prompt()).run(ctx)
    assert out.output["quests"] == ["Health"]


def test_pick_quest_unknown_quest_escalates(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"quests": ["Bogus"], "confidence": 0.9}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["vault_quests"] = _quests()
    with pytest.raises(EscalateToUser) as exc:
        PickQuest(prompt=_quest_prompt()).run(ctx)
    assert "Bogus" in exc.value.reason


def test_pick_quest_empty_list_escalates(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"quests": [], "confidence": 0.9}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["vault_quests"] = _quests()
    with pytest.raises(EscalateToUser):
        PickQuest(prompt=_quest_prompt()).run(ctx)


def test_pick_quest_no_vault_quests_escalates(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\n")
    ctx = _ctx(vault)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["vault_quests"] = []
    with pytest.raises(EscalateToUser):
        PickQuest(prompt=_quest_prompt()).run(ctx)


# ---- propose_filename ---------------------------------------------------


def _fn_prompt() -> Prompt:
    return Prompt(name="propose_filename", text="$title $body $para_type")


def test_propose_filename_happy_path(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(
        json.dumps({"choice": "generate", "filename": "Build Raised Beds.md", "reason": "ok"})
    )
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == "Build Raised Beds.md"
    assert out.meta["used_llm"] is True
    assert out.meta["choice"] == "generate"


def test_propose_filename_skips_llm_when_source_passes(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Chat With DeepWiki About Goose 2026-05-15.md"
    src.write_text("# Chat\n")
    llm = FakeLLM()
    # No response queued: if the step calls the LLM, FakeLLM raises.
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "resource"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == "Chat With DeepWiki About Goose 2026-05-15.md"
    assert out.meta["used_llm"] is False
    assert out.meta["choice"] == "keep"


def test_propose_filename_keeps_source_with_hyphen_separator(tmp_path: Path):
    # Regression for #34: a " - " separator (pure-punctuation word) must
    # not trip the structural check, so the source filename is kept as-is.
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Scikit-Learn Cheat Sheet - Python Machine Learning.md"
    src.write_text("# Sheet\n")
    llm = FakeLLM()
    # No response queued: if the step calls the LLM, FakeLLM raises.
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "resource"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == "Scikit-Learn Cheat Sheet - Python Machine Learning.md"
    assert out.meta["used_llm"] is False
    assert out.meta["choice"] == "keep"


def test_propose_filename_skip_still_checks_collision(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Existing.md"
    src.write_text("# X\n")
    (vault / "projects/Existing.md").write_text("---\ntype: project\n---\n")
    llm = FakeLLM()
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    with pytest.raises(EscalateToUser) as exc:
        ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert "collide" in exc.value.reason


def test_propose_filename_collision_escalates(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    (vault / "projects/Existing.md").write_text("---\ntype: project\n---\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "generate", "filename": "Existing.md"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    with pytest.raises(EscalateToUser) as exc:
        ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert "collide" in exc.value.reason


def test_propose_filename_ignores_archive_collision(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    (vault / "archive/projects/Old.md").write_text("---\ntype: project\n---\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "generate", "filename": "Old.md"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == "Old.md"


def test_propose_filename_path_separator_rejected(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "generate", "filename": "sub/Foo.md"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    with pytest.raises(EscalateToUser):
        ProposeFilename(prompt=_fn_prompt()).run(ctx)


def test_propose_filename_appends_md_suffix(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "generate", "filename": "Already Title"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == "Already Title.md"


@pytest.mark.parametrize(
    "bad",
    [
        "buildRaisedBeds.md",  # starts lowercase
        "iPhoneNotes.md",  # starts lowercase
    ],
)
def test_propose_filename_rejects_lowercase_start(tmp_path: Path, bad: str):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "generate", "filename": bad}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    with pytest.raises(EscalateToUser) as exc:
        ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert "title case" in exc.value.reason.lower()


def test_propose_filename_rejects_lowercase_joiner_at_start(tmp_path: Path):
    # Joiner words are only allowed in interior positions, not first/last.
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "generate", "filename": "on Sourdough Notes.md"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "resource"
    with pytest.raises(EscalateToUser) as exc:
        ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert "title case" in exc.value.reason.lower()


@pytest.mark.parametrize(
    "good",
    [
        "sklearn.linear_model.SGDClassifier.md",  # dotted Python identifier
        "RFC-2119.md",  # hyphen-joined ID
        "CVE-2021-44228.md",  # multi-hyphen ID
        "sgd_classifier_v2.md",  # snake_case identifier token
        "3D.printing.notes.md",  # leading-digit segment is fine
    ],
)
def test_propose_filename_accepts_identifier_style(tmp_path: Path, good: str):
    # Identifier-style stems are a second valid pattern alongside Title
    # Case: dot/hyphen/underscore-joined segments with no spaces. The LLM
    # may return them verbatim instead of forcing Title Case.
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "keep", "filename": good}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "resource"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == good


def test_propose_filename_auto_skips_identifier_source(tmp_path: Path):
    # A source basename that is already identifier-style auto-skips the
    # LLM, exactly like a Title Case source does.
    vault = _make_vault(tmp_path)
    src = vault / "inbox/sklearn.linear_model.SGDClassifier.md"
    src.write_text("# SGDClassifier\n")
    ctx = _ctx(vault)  # no LLM queued: must not be called
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "resource"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == "sklearn.linear_model.SGDClassifier.md"
    assert out.meta["used_llm"] is False


def test_propose_filename_accepts_identifier_snake_case(tmp_path: Path):
    # snake_case stems are now valid identifier-style names (e.g.
    # sgd_classifier_v2), so the LLM may return them verbatim.
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "keep", "filename": "build_raised_beds.md"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == "build_raised_beds.md"


def test_propose_filename_rejects_mixed_prose_and_identifier(tmp_path: Path):
    # The two patterns are distinct: a name with spaces AND a dotted
    # identifier segment is neither Title Case (last word starts lowercase)
    # nor identifier-style (has spaces), so it escalates.
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "generate", "filename": "Notes on sklearn.linear_model.md"}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "resource"
    with pytest.raises(EscalateToUser) as exc:
        ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert "identifier" in exc.value.reason.lower()


@pytest.mark.parametrize(
    "good",
    [
        "Run A 5K.md",  # "A" is uppercase anyway
        "Health.md",  # single word, no interior caps
        "Notes On Sourdough.md",  # "On" capitalized (was strict)
        "Notes on Sourdough.md",  # "on" is an interior joiner (#56)
        "Notes About Moon Landing and Dinosaurs.md",  # "and" is an interior joiner (#56)
        "Build Raised Beds.md",
        "Plan Family Reunion.md",
        "Chat With DeepWiki About Goose.md",  # brand name with interior caps in multi-word stem
        "A - B.md",  # "-" between words is pure punctuation, not a joiner (#34)
        "Scikit-Learn Cheat Sheet - Python Machine Learning.md",  # #34
        "Guide to the Galaxy.md",  # "to" and "the" are interior joiners (#56)
    ],
)
def test_propose_filename_accepts_strict_title_case(tmp_path: Path, good: str):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# Raw\n")
    llm = FakeLLM()
    llm.queue(json.dumps({"choice": "generate", "filename": good}))
    ctx = _ctx(vault, llm)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    out = ProposeFilename(prompt=_fn_prompt()).run(ctx)
    assert out.output["filename"] == good


# ---- plan_destination ---------------------------------------------------


def test_plan_destination_flat(tmp_path: Path):
    vault = _make_vault(tmp_path)
    ctx = _ctx(vault)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["filename"] = "Foo.md"
    out = PlanDestination().run(ctx)
    assert out.output["destination"] == "projects/Foo.md"


def test_plan_destination_resource(tmp_path: Path):
    vault = _make_vault(tmp_path)
    ctx = _ctx(vault)
    ctx.scratchpad["para_type"] = "resource"
    ctx.scratchpad["filename"] = "Trail Map.md"
    out = PlanDestination().run(ctx)
    assert out.output["destination"] == "resources/Trail Map.md"


# ---- apply_move (dry-run) -----------------------------------------------


def test_apply_move_dry_run_does_not_touch_disk(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# raw\nbody\n")
    (vault / "areas/Health.md").write_text("---\ntype: area\nquest: main\n---\n[[raw]] link\n")
    ctx = _ctx(vault)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["quests"] = ["Health"]
    ctx.scratchpad["filename"] = "Run a 5K.md"
    PlanDestination().run(ctx)
    out = ApplyMove(apply=False).run(ctx)

    assert src.exists()  # no move
    assert not (vault / "projects/Run a 5K.md").exists()
    assert out.output.wikilinks_rewritten == [{"file": "areas/Health.md", "occurrences": 1}]


def test_apply_move_dry_run_same_stem_reports_no_wikilink_rewrites(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\nbody\n")
    (vault / "areas/Health.md").write_text("---\ntype: area\nquest: main\n---\n[[Foo]] link\n")
    ctx = _ctx(vault)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["quests"] = ["Health"]
    ctx.scratchpad["filename"] = "Foo.md"  # same stem as source
    PlanDestination().run(ctx)
    out = ApplyMove(apply=False).run(ctx)

    assert out.output.wikilinks_rewritten == []


# ---- apply_move (apply) -------------------------------------------------


def test_apply_move_writes_files_and_rewrites_links(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# raw\nbody\n")
    (vault / "inbox/raw attachment.txt").write_text("att")
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\n---\n"
        "see [[raw]] and [[raw|the raw note]] and [[raw#section|alias]] and [[unrelated]]\n"
    )
    (vault / "archive/projects/Old.md").write_text("[[raw]] should NOT be rewritten\n")

    ctx = _ctx(vault)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["quests"] = ["Health"]
    ctx.scratchpad["filename"] = "Run a 5K.md"
    PlanDestination().run(ctx)
    out = ApplyMove(apply=True).run(ctx)

    moved = vault / "projects/Run a 5K.md"
    assert moved.exists()
    assert not src.exists()
    # Attachment moved + renamed.
    assert (vault / "projects/Run a 5K attachment.txt").exists()
    assert not (vault / "inbox/raw attachment.txt").exists()

    # Frontmatter merged.
    text = moved.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "type: project" in text
    assert "[[Health]]" in text

    # Wikilinks rewritten in non-archive file.
    health_text = (vault / "areas/Health.md").read_text(encoding="utf-8")
    assert "[[Run a 5K]]" in health_text
    assert "[[Run a 5K|the raw note]]" in health_text
    assert "[[Run a 5K#section|alias]]" in health_text
    assert "[[unrelated]]" in health_text  # untouched
    assert "[[raw" not in health_text

    # Archive untouched.
    assert "[[raw]]" in (vault / "archive/projects/Old.md").read_text(encoding="utf-8")

    # Reported.
    assert any(h["file"] == "areas/Health.md" for h in out.output.wikilinks_rewritten)


def test_apply_move_same_stem_reports_no_wikilink_rewrites(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/Foo.md"
    src.write_text("# Foo\nbody\n")
    link_note = vault / "areas/Health.md"
    original = "---\ntype: area\nquest: main\n---\nSee [[Foo]] for details.\n"
    link_note.write_text(original)

    ctx = _ctx(vault)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["quests"] = ["Health"]
    ctx.scratchpad["filename"] = "Foo.md"  # same stem as source
    PlanDestination().run(ctx)
    out = ApplyMove(apply=True).run(ctx)

    assert out.output.wikilinks_rewritten == []
    assert link_note.read_text(encoding="utf-8") == original


def test_apply_move_refuses_overwrite(tmp_path: Path):
    vault = _make_vault(tmp_path)
    src = vault / "inbox/raw.md"
    src.write_text("# raw\n")
    (vault / "projects/Run a 5K.md").write_text("existing\n")
    ctx = _ctx(vault)
    ScanNote(source=src).run(ctx)
    ctx.scratchpad["para_type"] = "project"
    ctx.scratchpad["quests"] = ["Health"]
    ctx.scratchpad["filename"] = "Run a 5K.md"
    PlanDestination().run(ctx)
    with pytest.raises(EscalateToUser):
        ApplyMove(apply=True).run(ctx)
