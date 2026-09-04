"""Per-step judge tests."""

from __future__ import annotations

from para_quest_notes.eval.fixtures import (
    Expected,
    ExpectedClassify,
    ExpectedDestination,
    ExpectedFilename,
    ExpectedPickQuest,
    ExpectedTemplateMerge,
)
from para_quest_notes.eval.judges import (
    canonical_filename,
    judge_classify_para,
    judge_pick_quest,
    judge_plan_destination,
    judge_propose_filename,
    judge_responds,
    judge_step,
    judge_template_merge,
)


def test_responds_passes_on_object_json() -> None:
    v = judge_responds('{"ok": true}')
    assert v.ok


def test_responds_fails_on_empty() -> None:
    v = judge_responds("")
    assert not v.ok and "empty" in v.reason


def test_responds_fails_on_non_object() -> None:
    v = judge_responds("[1,2,3]")
    assert not v.ok and "object" in v.reason


def test_responds_fails_on_garbage() -> None:
    v = judge_responds("not json")
    assert not v.ok and "unparseable" in v.reason


def test_classify_para_exact_match() -> None:
    exp = ExpectedClassify(type="project")
    assert judge_classify_para({"type": "project"}, exp).ok
    assert not judge_classify_para({"type": "area"}, exp).ok
    assert not judge_classify_para(None, exp).ok


def test_pick_quest_set_equality() -> None:
    exp = ExpectedPickQuest(
        acceptable=(frozenset({"Health"}), frozenset({"Health", "Connect"})),
    )
    assert judge_pick_quest({"quests": ["Health"]}, exp).ok
    assert judge_pick_quest({"quests": ["Connect", "Health"]}, exp).ok
    assert not judge_pick_quest({"quests": ["Connect"]}, exp).ok
    assert not judge_pick_quest({"quests": []}, exp).ok


def test_pick_quest_skipped() -> None:
    exp = ExpectedPickQuest(skipped=True)
    assert judge_pick_quest({"quests": [], "skipped": True}, exp).ok
    assert not judge_pick_quest({"quests": ["Health"]}, exp).ok


def test_pick_quest_skipped_when_expected_to_run() -> None:
    exp = ExpectedPickQuest(acceptable=(frozenset({"Health"}),))
    v = judge_pick_quest({"quests": [], "skipped": True}, exp)
    assert not v.ok and "expected" in v.reason.lower()


def test_canonical_filename_normalizes() -> None:
    assert canonical_filename("Run a 5K.md") == "run a 5k"
    assert canonical_filename("run-a-5k.md") == "run a 5k"
    assert canonical_filename("Run_a_5K") == "run a 5k"
    assert canonical_filename("  Run  a  5K  ") == "run a 5k"


def test_propose_filename_canonical_match() -> None:
    exp = ExpectedFilename(acceptable=("run a 5k",))
    assert judge_propose_filename({"filename": "Run a 5K.md"}, exp).ok
    assert judge_propose_filename({"filename": "run-a-5k.md"}, exp).ok
    assert not judge_propose_filename({"filename": "Train Plan.md"}, exp).ok


def test_propose_filename_acceptable_set_matches_any() -> None:
    exp = ExpectedFilename(acceptable=("sourdough starter notes", "sourdough starter"))
    assert judge_propose_filename({"filename": "Sourdough Starter.md"}, exp).ok
    assert judge_propose_filename({"filename": "Sourdough Starter Notes.md"}, exp).ok
    v = judge_propose_filename({"filename": "Notes.md"}, exp)
    assert not v.ok and "no acceptable name" in v.reason


def test_propose_filename_handles_non_string() -> None:
    exp = ExpectedFilename(acceptable=("x",))
    v = judge_propose_filename({"filename": 42}, exp)
    assert not v.ok and "string" in v.reason


def test_plan_destination_exact() -> None:
    exp = ExpectedDestination(destination="projects/Foo.md")
    assert judge_plan_destination({"destination": "projects/Foo.md"}, exp).ok
    assert not judge_plan_destination({"destination": "areas/Foo.md"}, exp).ok


def test_template_merge_requires_exact_placement_mapping() -> None:
    expected = ExpectedTemplateMerge(
        placements=(("block-001", "section-002"), ("block-002", "unsorted"))
    )
    assert judge_template_merge(
        {
            "status": "merged",
            "placements": [
                {"block_id": "block-001", "section_id": "section-002"},
                {"block_id": "block-002", "section_id": "unsorted"},
            ],
        },
        expected,
    ).ok
    assert not judge_template_merge(
        {
            "status": "merged",
            "placements": [
                {"block_id": "block-001", "section_id": "section-003"},
                {"block_id": "block-002", "section_id": "unsorted"},
            ],
        },
        expected,
    ).ok


def test_judge_step_dispatches() -> None:
    exp = Expected(classify_para=ExpectedClassify(type="resource"))
    v = judge_step("classify_para", {"type": "resource"}, exp)
    assert v.ok and v.step == "classify_para"


def test_judge_step_fails_when_no_expectation() -> None:
    exp = Expected()
    v = judge_step("classify_para", {"type": "resource"}, exp)
    assert not v.ok and "no expected" in v.reason
