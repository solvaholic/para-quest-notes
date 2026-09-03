"""Tests for shell completion (#121).

Two layers, deliberately:

* direct unit tests of candidate generation, which is where the vault
  semantics live; and
* one end-to-end argcomplete *protocol* test per shape (static and
  dynamic), driven through the real ``CompletionFinder`` so the wiring
  is proven rather than assumed.

Nothing here depends on an interactive shell or the user's dotfiles.
"""

from __future__ import annotations

import argparse
import importlib
import io
import os
import subprocess
import sys
import tomllib
from argparse import Namespace
from pathlib import Path

import argcomplete
import pytest

from para_quest_notes.adapter.completion import (
    complete_archive_targets,
    complete_daily_targets,
    complete_quest_wikilinks,
    complete_quests,
    complete_sub_paths,
    complete_templates,
    enable_completion,
    resolve_context,
    set_completer,
)
from para_quest_notes.workflows.create.templates import resolve_template_path

REPO_ROOT = Path(__file__).resolve().parents[2]
IFS = "\013"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A small vault with Quests, sub-paths, templates, and targets."""
    v = tmp_path / "vault"
    (v / "areas").mkdir(parents=True)
    (v / "projects" / "2026" / "Home").mkdir(parents=True)
    (v / "areas" / "Home").mkdir(parents=True)
    (v / "areas" / "2026").mkdir()
    (v / "resources" / "templates").mkdir(parents=True)
    (v / "resources" / "daily_notes" / "2026" / "08").mkdir(parents=True)
    (v / "inbox").mkdir()

    (v / "areas" / "Health.md").write_text("---\nquest-kind: main\n---\n# Health\n")
    (v / "areas" / "Side Gig.md").write_text("---\nquest-kind: side\n---\n# Side Gig\n")
    (v / "areas" / "Not A Quest.md").write_text("---\ntype: area\n---\n# Not A Quest\n")

    (v / "resources" / "templates" / "note.md").write_text("# $title\n")
    (v / "resources" / "templates" / "meeting.md").write_text("# $title\n")

    (v / "projects" / "2026" / "Ship It.md").write_text("# Ship It\n")
    (v / "projects" / "Repaint The Shed.md").write_text("# Repaint The Shed\n")

    (v / "inbox" / "2026-08-22.md").write_text("# 2026-08-22\n")
    (v / "resources" / "daily_notes" / "2026" / "08" / "2026-08-01.md").write_text("# x\n")
    return v


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Neutralize ambient vault/config so tests see only what they set up."""
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no-such-config"))
    monkeypatch.chdir(tmp_path)


def args_for(vault: Path | None = None, **extra: object) -> Namespace:
    return Namespace(vault=vault, config=None, **extra)


# --------------------------------------------------------------------------- #
# argcomplete protocol driver (no shell, no subprocess)
# --------------------------------------------------------------------------- #


class _Exited(Exception):
    pass


class _TestFinder(argcomplete.CompletionFinder):
    """``CompletionFinder`` that leaves file descriptor 9 alone.

    argcomplete's default debug stream reopens fd 9, which pytest is
    already using for its faulthandler dup. argcomplete documents
    overriding this hook for exactly that clash.
    """

    def _init_debug_stream(self) -> None:
        pass


def complete(
    parser: argparse.ArgumentParser,
    comp_line: str,
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Run one real completion round for ``comp_line`` and return candidates."""
    for key, value in {
        "_ARGCOMPLETE": "1",
        "_ARGCOMPLETE_IFS": IFS,
        "_ARGCOMPLETE_SHELL": "bash",
        "_ARGCOMPLETE_COMP_WORDBREAKS": " \t\n\"'><=;|&(:",
        "COMP_LINE": comp_line,
        "COMP_POINT": str(len(comp_line)),
        "COMP_TYPE": "9",
    }.items():
        monkeypatch.setenv(key, value)

    stream = io.StringIO()

    def _exit(code: int) -> None:
        raise _Exited(code)

    finder = _TestFinder()
    with pytest.raises(_Exited):
        finder(parser, exit_method=_exit, output_stream=stream)

    return [c.strip().replace("\\", "") for c in stream.getvalue().split(IFS) if c.strip()]


# --------------------------------------------------------------------------- #
# argparse stays the source of truth for static values
# --------------------------------------------------------------------------- #


def test_static_choices_come_from_argparse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Completion reads ``choices=`` off the parser, not a shell-side copy."""
    parser = argparse.ArgumentParser(prog="pqn-demo")
    parser.add_argument("--group-by", choices=("due", "quest", "area"))

    assert complete(parser, "pqn-demo --group-by ", monkeypatch) == ["due", "quest", "area"]

    # Change the parser and the completion follows - proving there is no
    # duplicated static list anywhere downstream.
    parser = argparse.ArgumentParser(prog="pqn-demo")
    parser.add_argument("--group-by", choices=("sprint",))
    assert complete(parser, "pqn-demo --group-by ", monkeypatch) == ["sprint"]


@pytest.mark.parametrize(
    ("module_name", "comp_line", "expected"),
    [
        (
            "para_quest_notes.workflows.create.cli",
            "pqn-create --type ",
            ["project", "area", "resource"],
        ),
        (
            "para_quest_notes.workflows.create.cli",
            "pqn-create --quest-kind ",
            ["main", "side", "none"],
        ),
        (
            "para_quest_notes.workflows.tasks.cli",
            "pqn-tasks --group-by ",
            ["due", "quest", "area"],
        ),
        (
            "para_quest_notes.workflows.tasks.cli",
            "pqn-tasks --date-field ",
            ["due", "scheduled", "start"],
        ),
        (
            "para_quest_notes.workflows.tasks.cli",
            "pqn-tasks --type ",
            ["project", "area", "resource"],
        ),
        (
            "para_quest_notes.workflows.search.cli",
            "pqn-search --type ",
            ["project", "area", "resource"],
        ),
        (
            "para_quest_notes.workflows.quests.cli",
            "pqn-quests --type ",
            ["project", "area", "resource"],
        ),
        ("para_quest_notes.workflows.validate.cli", "pqn-validate --severity ", None),
        ("para_quest_notes.workflows.validate.cli", "pqn-validate --check ", None),
        ("para_quest_notes.workflows.config.cli", "pqn-config --section ", None),
        (
            "para_quest_notes.workflows.ingest_inbox.cli",
            "pqn-ingest --format ",
            ["json", "text"],
        ),
    ],
)
def test_workflow_choices_complete(
    module_name: str,
    comp_line: str,
    expected: list[str] | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(module_name)
    parser = module.build_parser()
    got = complete(parser, comp_line, monkeypatch)

    flag = comp_line.split()[-1]
    action = next(a for a in parser._actions if flag in a.option_strings)
    assert got == list(action.choices)
    if expected is not None:
        assert got == expected


def test_suppressed_quest_alias_is_not_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deprecated ``pqn-create --quest`` stays hidden from completion (#98)."""
    from para_quest_notes.workflows.create.cli import build_parser

    options = complete(build_parser(), "pqn-create --", monkeypatch)
    assert "--quest-kind" in options
    assert "--quest" not in options


# --------------------------------------------------------------------------- #
# Every installed entry point enables completion before parsing
# --------------------------------------------------------------------------- #


def _installed_entry_points() -> list[tuple[str, str, str]]:
    raw = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = raw["project"]["scripts"]
    out = []
    for command, target in scripts.items():
        module_name, func_name = target.split(":")
        out.append((command, module_name, func_name))
    return sorted(out)


def test_all_entry_points_are_declared() -> None:
    commands = [c for c, _, _ in _installed_entry_points()]
    assert commands == sorted(
        [
            "pqn-archive",
            "pqn-config",
            "pqn-create",
            "pqn-daily",
            "pqn-eval",
            "pqn-ingest",
            "pqn-quests",
            "pqn-search",
            "pqn-tasks",
            "pqn-validate",
        ]
    )


@pytest.mark.parametrize(
    ("command", "module_name", "func_name"),
    _installed_entry_points(),
    ids=[c for c, _, _ in _installed_entry_points()],
)
def test_entry_point_enables_completion_before_parsing(
    command: str,
    module_name: str,
    func_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--help`` exits during ``parse_args``, so reaching it proves ordering."""
    module = importlib.import_module(module_name)
    calls: list[argparse.ArgumentParser] = []

    monkeypatch.setattr(module, "enable_completion", calls.append)
    with pytest.raises(SystemExit):
        getattr(module, func_name)(["--help"])

    assert len(calls) == 1, f"{command} did not enable completion exactly once"
    assert isinstance(calls[0], argparse.ArgumentParser)


# --------------------------------------------------------------------------- #
# Quest candidates
# --------------------------------------------------------------------------- #


def test_quest_completion_returns_bare_names(vault: Path) -> None:
    assert complete_quests(parsed_args=args_for(vault)) == ["Health", "Side Gig"]


def test_supports_completion_returns_wikilinks(vault: Path) -> None:
    """``--supports`` requires wikilink syntax today, so completion emits it."""
    assert complete_quest_wikilinks(parsed_args=args_for(vault)) == ["[[Health]]", "[[Side Gig]]"]


def test_quest_completion_skips_non_quest_areas(vault: Path) -> None:
    assert "Not A Quest" not in complete_quests(parsed_args=args_for(vault))


# --------------------------------------------------------------------------- #
# --sub-path candidates
# --------------------------------------------------------------------------- #


def test_sub_path_respects_parsed_type(vault: Path) -> None:
    got = complete_sub_paths(parsed_args=args_for(vault, type="project"))
    assert got == ["2026", "2026/Home"]


def test_sub_path_without_type_unions_and_dedupes(vault: Path) -> None:
    """``2026`` exists under both projects/ and areas/ but appears once."""
    got = complete_sub_paths(parsed_args=args_for(vault, type=None))
    assert got.count("2026") == 1
    assert {"2026", "2026/Home", "Home", "templates"} <= set(got)


# --------------------------------------------------------------------------- #
# --template candidates
# --------------------------------------------------------------------------- #


def test_template_completion_values_are_accepted_by_the_resolver(vault: Path) -> None:
    got = complete_templates(parsed_args=args_for(vault))
    assert got == ["meeting", "note"]
    for value in got:
        assert resolve_template_path(value, vault=vault) is not None


def test_template_completion_honors_configured_template_dir(
    vault: Path, tmp_path: Path, isolated_env: None
) -> None:
    custom = vault / "resources" / "my templates"
    custom.mkdir()
    (custom / "weekly.md").write_text("# $title\n")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "workflows:\n  create:\n    template_dir: 'resources/my templates'\n",
        encoding="utf-8",
    )

    parsed = Namespace(vault=vault, config=config_path)
    assert complete_templates(parsed_args=parsed) == ["weekly"]


# --------------------------------------------------------------------------- #
# pqn-daily / pqn-archive targets
# --------------------------------------------------------------------------- #


def test_daily_targets_match_resolve_target_scope(vault: Path) -> None:
    (vault / "2026-07-04.md").write_text("# x\n")
    # A daily-shaped note somewhere ResolveTarget will not search.
    (vault / "projects" / "2026-01-01.md").write_text("# x\n")
    # An inbox note that isn't a daily note at all.
    (vault / "inbox" / "Random Thought.md").write_text("# x\n")

    got = complete_daily_targets(parsed_args=args_for(vault))
    assert got == ["2026-07-04", "2026-08-01", "2026-08-22"]


def test_archive_targets_are_projects_only(vault: Path) -> None:
    (vault / "projects" / "archive").mkdir()
    (vault / "projects" / "archive" / "Old Thing.md").write_text("# x\n")

    got = complete_archive_targets(parsed_args=args_for(vault))
    assert got == ["Repaint The Shed", "Ship It"]


def test_duplicate_basenames_complete_as_vault_relative_paths(vault: Path) -> None:
    """A bare stem that resolves two ways would be rejected, so emit paths."""
    (vault / "projects" / "2026" / "Home" / "Ship It.md").write_text("# x\n")

    got = complete_archive_targets(parsed_args=args_for(vault))
    assert "Ship It" not in got
    assert "projects/2026/Ship It.md" in got
    assert "projects/2026/Home/Ship It.md" in got
    # Unambiguous siblings keep the nicer bare form.
    assert "Repaint The Shed" in got


# --------------------------------------------------------------------------- #
# Vault + config precedence
# --------------------------------------------------------------------------- #


def test_explicit_vault_flag_wins(
    vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_env: None
) -> None:
    other = tmp_path / "other"
    (other / "areas").mkdir(parents=True)
    (other / "projects").mkdir()
    monkeypatch.setenv("PARA_QUEST_VAULT", str(other))

    resolved, _ = resolve_context(args_for(vault))
    assert resolved == vault.resolve()
    assert complete_quests(parsed_args=args_for(vault)) == ["Health", "Side Gig"]


def test_env_var_is_honored(
    vault: Path, monkeypatch: pytest.MonkeyPatch, isolated_env: None
) -> None:
    monkeypatch.setenv("PARA_QUEST_VAULT", str(vault))
    assert complete_quests(parsed_args=args_for(None)) == ["Health", "Side Gig"]


def test_cwd_discovery_is_honored(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    monkeypatch.chdir(vault / "projects" / "2026")
    assert complete_quests(parsed_args=args_for(None)) == ["Health", "Side Gig"]


def test_config_vault_is_the_last_rung(vault: Path, tmp_path: Path, isolated_env: None) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"vault: {vault}\n", encoding="utf-8")

    parsed = Namespace(vault=None, config=config_path)
    assert complete_quests(parsed_args=parsed) == ["Health", "Side Gig"]


# --------------------------------------------------------------------------- #
# Expected failures stay quiet
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "completer",
    [
        complete_quests,
        complete_quest_wikilinks,
        complete_sub_paths,
        complete_templates,
        complete_daily_targets,
        complete_archive_targets,
    ],
)
def test_unresolved_vault_yields_nothing_quietly(
    completer: object,
    capsys: pytest.CaptureFixture[str],
    isolated_env: None,
) -> None:
    assert completer(parsed_args=Namespace(vault=None, config=None, type=None)) == []  # type: ignore[operator]
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


def test_missing_optional_directories_yield_nothing_quietly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = tmp_path / "bare"
    (bare / "areas").mkdir(parents=True)
    (bare / "projects").mkdir()

    parsed = args_for(bare, type=None)
    assert complete_templates(parsed_args=parsed) == []
    assert complete_daily_targets(parsed_args=parsed) == []
    assert complete_archive_targets(parsed_args=parsed) == []
    assert complete_quests(parsed_args=parsed) == []
    assert capsys.readouterr().err == ""


def test_unreadable_candidate_is_skipped_quietly(
    vault: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_read = Path.read_text

    def boom(self: Path, *a: object, **kw: object) -> str:
        if self.name == "Health.md":
            raise PermissionError(self)
        return real_read(self, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", boom)
    assert complete_quests(parsed_args=args_for(vault)) == ["Side Gig"]
    assert capsys.readouterr().err == ""


def test_malformed_config_does_not_break_static_completion(
    vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_env: None
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- not: a mapping\n", encoding="utf-8")

    from para_quest_notes.workflows.tasks.cli import build_parser

    line = f"pqn-tasks --config {config_path} --group-by "
    assert complete(build_parser(), line, monkeypatch) == ["due", "quest", "area"]


def test_legacy_quest_key_warning_is_suppressed(
    vault: Path, capsys: pytest.CaptureFixture[str], recwarn: pytest.WarningsRecorder
) -> None:
    (vault / "areas" / "Legacy.md").write_text("---\nquest: main\n---\n# Legacy\n")

    assert "Legacy" in complete_quests(parsed_args=args_for(vault))
    assert capsys.readouterr().err == ""
    assert len(recwarn) == 0


# --------------------------------------------------------------------------- #
# Read-only guarantees
# --------------------------------------------------------------------------- #


def _snapshot(root: Path) -> dict[str, tuple[int, float]]:
    return {
        str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_completion_does_not_mutate_the_sample_vault() -> None:
    sample = REPO_ROOT / "samples" / "vault"
    before = _snapshot(sample)

    parsed = args_for(sample, type=None)
    for completer in (
        complete_quests,
        complete_sub_paths,
        complete_templates,
        complete_daily_targets,
        complete_archive_targets,
    ):
        completer(parsed_args=parsed)

    assert _snapshot(sample) == before


def test_completion_never_instantiates_an_llm_client(
    vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import para_quest_notes.adapter.llm as llm_module

    def forbidden(*a: object, **kw: object) -> None:
        raise AssertionError("completion must not talk to Ollama")

    monkeypatch.setattr(llm_module.OllamaClient, "__init__", forbidden)

    parsed = args_for(vault, type=None)
    complete_quests(parsed_args=parsed)
    complete_archive_targets(parsed_args=parsed)


def test_end_to_end_protocol_run_is_read_only(vault: Path, tmp_path: Path) -> None:
    """A real subprocess completion round: candidates out, no side effects.

    Drives argcomplete's actual wire protocol (``_ARGCOMPLETE`` plus
    ``COMP_LINE``, candidates written to file descriptor 8) rather than
    an interactive shell, so CI needs no dotfiles.
    """
    state = tmp_path / "state"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"run_log_dir: {state}\n", encoding="utf-8")

    out_path = tmp_path / "completions"
    line = f"pqn-archive --config {config_path} --vault {vault} "
    env = {
        **os.environ,
        "_ARGCOMPLETE": "1",
        "_ARGCOMPLETE_IFS": IFS,
        "_ARGCOMPLETE_SHELL": "bash",
        # argcomplete's own escape hatch for the fd-8 convention, so the
        # test needs no shell redirection.
        "_ARGCOMPLETE_STDOUT_FILENAME": str(out_path),
        "COMP_LINE": line,
        "COMP_POINT": str(len(line)),
    }
    env.pop("PARA_QUEST_VAULT", None)

    proc = subprocess.run(
        [sys.executable, "-m", "para_quest_notes.workflows.archive.cli"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )

    candidates = [
        c.strip().replace("\\", "")
        for c in out_path.read_text(encoding="utf-8").split(IFS)
        if c.strip()
    ]
    assert "Repaint The Shed" in candidates
    assert "Ship It" in candidates
    assert proc.stderr == b""
    assert not state.exists(), "completion created a run log directory"


# --------------------------------------------------------------------------- #
# Normal (non-completion) behavior is untouched
# --------------------------------------------------------------------------- #


def test_enable_completion_is_a_noop_without_argcomplete_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for key in ("_ARGCOMPLETE", "COMP_LINE", "COMP_POINT"):
        monkeypatch.delenv(key, raising=False)

    parser = argparse.ArgumentParser(prog="pqn-demo")
    parser.add_argument("--flag")
    enable_completion(parser)

    assert parser.parse_args(["--flag", "value"]).flag == "value"
    assert capsys.readouterr().out == ""


def test_set_completer_attaches_and_returns_the_action() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_argument("--thing")
    returned = set_completer(action, complete_quests)

    assert returned is action
    assert action.completer is complete_quests  # type: ignore[attr-defined]
