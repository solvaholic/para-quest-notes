"""Per-step tests for ``pqn-create``."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext
from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.steps.check_collision import CheckCollision
from para_quest_notes.workflows.create.steps.compose_note import ComposeNote
from para_quest_notes.workflows.create.steps.compute_destination import ComputeDestination
from para_quest_notes.workflows.create.steps.validate_after import ValidateAfter
from para_quest_notes.workflows.create.steps.validate_inputs import ValidateInputs
from para_quest_notes.workflows.create.steps.write_note import WriteNote


def _ctx(vault: Path | None = None) -> StepContext:
    return StepContext(workflow="create", run_id="test", vault=vault)


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def test_validate_inputs_happy_project():
    inputs = CreateInputs(title="My Plan", type="project", supports=["[[Health]]"])
    ctx = _ctx()
    ValidateInputs(inputs).run(ctx)
    assert ctx.scratchpad["title"] == "My Plan"
    assert ctx.scratchpad["sub_path"] == ""


def test_validate_inputs_rejects_camel_case():
    inputs = CreateInputs(title="myPlan", type="project", supports=["[[Health]]"])
    with pytest.raises(EscalateToUser) as exc:
        ValidateInputs(inputs).run(_ctx())
    assert "Title Case" in exc.value.reason


@pytest.mark.parametrize(
    "title",
    ["Probe LeCun AI Architecture", "McDonald Research", "iPhone Setup"],
)
def test_validate_inputs_allows_mixed_case_proper_nouns(title: str):
    inputs = CreateInputs(title=title, type="project", supports=["[[Health]]"])
    ValidateInputs(inputs).run(_ctx())


def test_validate_inputs_rejects_bad_chars():
    inputs = CreateInputs(title="My/Plan", type="project", supports=["[[Health]]"])
    with pytest.raises(EscalateToUser):
        ValidateInputs(inputs).run(_ctx())


def test_validate_inputs_allows_missing_supports_for_project():
    inputs = CreateInputs(title="My Plan", type="project")
    ctx = _ctx()
    result = ValidateInputs(inputs).run(ctx)
    assert result.output["notes"] == [
        "filed to inbox because no --supports was provided for type=project"
    ]
    assert ctx.scratchpad["inputs"].supports is None


def test_validate_inputs_allows_missing_supports_for_area():
    inputs = CreateInputs(title="Home", type="area")
    ctx = _ctx()
    result = ValidateInputs(inputs).run(ctx)
    assert result.output["notes"] == [
        "filed to inbox because no --supports was provided for type=area"
    ]


def test_validate_inputs_infers_supports_for_quest_main():
    """--quest main without --supports infers supports=[[<title>]]."""
    inputs = CreateInputs(title="Coffee", type="area", quest="main")
    ctx = _ctx()
    result = ValidateInputs(inputs).run(ctx)
    assert result.output["notes"] == []
    assert ctx.scratchpad["inputs"].supports == ["[[Coffee]]"]


def test_validate_inputs_quest_main_does_not_override_explicit_supports():
    """Explicit --supports is kept even with --quest main."""
    inputs = CreateInputs(title="Coffee", type="area", quest="main", supports=["[[Brewing]]"])
    ctx = _ctx()
    result = ValidateInputs(inputs).run(ctx)
    assert result.output["notes"] == []
    assert ctx.scratchpad["inputs"].supports == ["[[Brewing]]"]


def test_validate_inputs_resource_must_be_quest_none():
    inputs = CreateInputs(title="A Read", type="resource", quest="main")
    with pytest.raises(EscalateToUser):
        ValidateInputs(inputs).run(_ctx())


def test_validate_inputs_rejects_bad_wikilink():
    inputs = CreateInputs(title="X", type="project", supports=["Health"])
    with pytest.raises(EscalateToUser):
        ValidateInputs(inputs).run(_ctx())


def test_validate_inputs_rejects_path_traversal():
    inputs = CreateInputs(
        title="X",
        type="project",
        supports=["[[Health]]"],
        sub_path="../escape",
    )
    with pytest.raises(EscalateToUser):
        ValidateInputs(inputs).run(_ctx())


def test_compute_destination_basic(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        inputs=CreateInputs(title="My Plan", type="project", supports=["[[Health]]"]),
        title="My Plan",
        sub_path="",
    )
    ComputeDestination().run(ctx)
    assert ctx.scratchpad["destination"] == "projects/My Plan.md"
    assert ctx.scratchpad["destination_mode"] == "canonical"
    assert ctx.scratchpad["destination_abs"] == vault / "projects" / "My Plan.md"


def test_compute_destination_with_subpath(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        inputs=CreateInputs(
            title="Garden", type="area", supports=["[[Home]]"], sub_path="Home/Outside"
        ),
        title="Garden",
        sub_path="Home/Outside",
    )
    ComputeDestination().run(ctx)
    assert ctx.scratchpad["destination"] == "areas/Home/Outside/Garden.md"


def test_compute_destination_inbox_without_supports(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        inputs=CreateInputs(title="Garden", type="area"),
        title="Garden",
        sub_path="Home/Outside",
    )
    ComputeDestination().run(ctx)
    assert ctx.scratchpad["destination"] == "inbox/Garden.md"
    assert ctx.scratchpad["destination_mode"] == "inbox"


def test_check_collision_clean(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        filename="Brand New.md",
        destination="projects/Brand New.md",
        destination_abs=vault / "projects" / "Brand New.md",
    )
    result = CheckCollision().run(ctx)
    assert result.output["collisions"] == []


def test_check_collision_destination_exists(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "Existing.md").write_text("# x\n")
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        filename="Existing.md",
        destination="projects/Existing.md",
        destination_abs=vault / "projects" / "Existing.md",
    )
    with pytest.raises(EscalateToUser) as exc:
        CheckCollision().run(ctx)
    assert "already exists" in exc.value.reason


def test_check_collision_basename_dup(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "areas" / "Twin.md").write_text("# x\n")
    ctx = _ctx(vault)
    ctx.scratchpad.update(
        filename="Twin.md",
        destination="projects/Twin.md",
        destination_abs=vault / "projects" / "Twin.md",
    )
    with pytest.raises(EscalateToUser):
        CheckCollision().run(ctx)


def test_compose_note_project(tmp_path: Path):
    ctx = _ctx()
    ctx.scratchpad.update(
        inputs=CreateInputs(title="My Plan", type="project", supports=["[[Health]]"]),
        title="My Plan",
    )
    ComposeNote(today="2026-01-02").run(ctx)
    content = ctx.scratchpad["content"]
    assert content.startswith("---\n")
    assert "type: project" in content
    assert "supports:" in content
    assert "[[Health]]" in content
    assert "created: '2026-01-02'" in content or "created: 2026-01-02" in content
    assert "# My Plan" in content
    assert "## Tasks" in content


def test_compose_note_resource_drops_empty_supports(tmp_path: Path):
    ctx = _ctx()
    ctx.scratchpad.update(
        inputs=CreateInputs(
            title="Cool Read", type="resource", quest="none", source_url="https://x"
        ),
        title="Cool Read",
    )
    ComposeNote(today="2026-01-02").run(ctx)
    content = ctx.scratchpad["content"]
    assert "supports:" not in content
    assert "source_url: https://x" in content
    assert "https://x" in content  # surfaced in Source block too


def test_write_note_dry_run_no_write(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault)
    dest = vault / "projects" / "X.md"
    ctx.scratchpad.update(
        destination_abs=dest,
        destination="projects/X.md",
        content="---\ntype: project\n---\n# X\n",
    )
    WriteNote(apply=False).run(ctx)
    assert not dest.exists()


def test_write_note_apply_writes(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault)
    dest = vault / "projects" / "X.md"
    ctx.scratchpad.update(
        destination_abs=dest,
        destination="projects/X.md",
        content="---\ntype: project\n---\n# X\n",
    )
    WriteNote(apply=True).run(ctx)
    assert dest.exists()
    assert dest.read_text() == "---\ntype: project\n---\n# X\n"


def test_write_note_apply_refuses_overwrite(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault)
    dest = vault / "projects" / "X.md"
    dest.write_text("preexisting")
    ctx.scratchpad.update(
        destination_abs=dest,
        destination="projects/X.md",
        content="new",
    )
    with pytest.raises(EscalateToUser):
        WriteNote(apply=True).run(ctx)


def test_validate_after_skips_on_dry_run(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    ctx = _ctx(vault)
    ctx.scratchpad["destination_abs"] = vault / "projects" / "Z.md"
    res = ValidateAfter(apply=False).run(ctx)
    assert res.output == {"skipped": True, "issues": []}
