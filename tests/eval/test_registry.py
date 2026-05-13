from __future__ import annotations

from para_quest_notes.eval.registry import get_evaluable_step, parse_step_ref, register_defaults


def test_registry_roundtrip_returns_registered_step() -> None:
    register_defaults()
    workflow, name = parse_step_ref("ingest:classify_para")
    step = get_evaluable_step(workflow, name)
    assert step is get_evaluable_step("ingest", "classify_para")
    assert step.ref == "ingest:classify_para"


def test_bare_step_name_defaults_to_ingest() -> None:
    workflow, name = parse_step_ref("classify_para")
    assert (workflow, name) == ("ingest", "classify_para")
