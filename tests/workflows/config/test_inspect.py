"""Unit tests for the ``pqn-config`` inspector (provenance + resolution)."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.config import Config, OllamaConfig, load_config
from para_quest_notes.workflows.config.inspect import inspect_config


def _mk_vault(root: Path) -> Path:
    (root / "areas").mkdir(parents=True)
    (root / "projects").mkdir(parents=True)
    return root


def test_defaults_when_no_config_file(tmp_path: Path) -> None:
    config = Config(source_path=tmp_path / "absent.yaml")
    report = inspect_config(config=config, env={}, start_dir=tmp_path)

    assert report.models.default_model.value == "granite4.1:30b"
    assert report.models.default_model.source == "default"
    assert report.ollama.base_url.source == "default"
    assert report.paths.config_found is False


def test_config_provenance_from_yaml(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "ollama:\n"
        "  default_model: custom:latest\n"
        "  request_timeout_seconds: 45\n"
        "workflows:\n"
        "  create:\n"
        "    template_dir: my/templates\n"
        "run_log_dir: /tmp/pqn-runs\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)
    report = inspect_config(config=config, env={}, start_dir=tmp_path)

    assert report.models.default_model.value == "custom:latest"
    assert report.models.default_model.source == "config"
    # base_url wasn't set even though the ollama block exists.
    assert report.ollama.base_url.source == "default"
    assert report.ollama.request_timeout_seconds.source == "config"
    assert report.templates.template_dir.value == "my/templates"
    assert report.templates.template_dir.source == "config"
    assert report.paths.run_log_dir.value == "/tmp/pqn-runs"
    assert report.paths.run_log_dir.source == "config"
    assert report.paths.config_found is True


def test_vault_resolves_via_flag(tmp_path: Path) -> None:
    vault = _mk_vault(tmp_path / "v")
    config = Config(source_path=tmp_path / "absent.yaml")
    report = inspect_config(config=config, vault_arg=vault, env={}, start_dir=tmp_path)

    assert report.vault.resolved is True
    assert report.vault.source == "flag"
    assert report.vault.path == str(vault.resolve())


def test_vault_unresolved_is_reported_not_raised(tmp_path: Path) -> None:
    config = Config(source_path=tmp_path / "absent.yaml")
    report = inspect_config(config=config, env={}, start_dir=tmp_path)

    assert report.vault.resolved is False
    assert report.vault.path is None
    assert report.vault.error is not None


def test_per_workflow_model_override_flagged_not_honored(tmp_path: Path) -> None:
    config = Config(
        source_path=tmp_path / "absent.yaml",
        workflows={"ingest": {"model": "qwen3:30b"}, "archive": {"model": "x:1"}},
    )
    report = inspect_config(config=config, env={}, start_dir=tmp_path)

    overrides = {o.workflow: o for o in report.models.overrides}
    assert set(overrides) == {"archive", "ingest"}
    assert overrides["ingest"].model == "qwen3:30b"
    # No workflow reads its per-workflow model today — drift is surfaced.
    assert all(o.honored is False for o in report.models.overrides)


def test_tasks_date_fields_reports_config_provenance_and_honored(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "workflows:\n  tasks:\n    date_fields: [scheduled, due]\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)

    report = inspect_config(config=config, env={}, start_dir=tmp_path)

    assert report.tasks.date_fields.value == ["scheduled", "due"]
    assert report.tasks.date_fields.source == "config"
    assert report.tasks.date_fields.honored is True


def test_tasks_date_fields_reports_default(tmp_path: Path) -> None:
    config = Config(source_path=tmp_path / "absent.yaml")

    report = inspect_config(config=config, env={}, start_dir=tmp_path)

    assert report.tasks.date_fields.value == ["due", "scheduled", "start"]
    assert report.tasks.date_fields.source == "default"
    assert report.tasks.date_fields.honored is True


def test_daily_settings_report_config_and_default_provenance(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "workflows:\n  daily:\n    create_missing: true\n    editor: [code, --reuse-window]\n",
        encoding="utf-8",
    )
    config = load_config(cfg_file)

    report = inspect_config(config=config, env={}, start_dir=tmp_path)

    assert report.daily.create_missing.value is True
    assert report.daily.create_missing.source == "config"
    assert report.daily.open_existing.value is False
    assert report.daily.open_existing.source == "default"
    assert report.daily.editor.value == ["code", "--reuse-window"]
    assert report.daily.editor.source == "config"


def test_template_files_listed_when_dir_exists(tmp_path: Path) -> None:
    vault = _mk_vault(tmp_path / "v")
    tdir = vault / "resources" / "templates"
    tdir.mkdir(parents=True)
    (tdir / "note.md").write_text("x", encoding="utf-8")
    (tdir / "project.md").write_text("x", encoding="utf-8")
    (tdir / "ignore.txt").write_text("x", encoding="utf-8")
    config = Config(source_path=tmp_path / "absent.yaml")

    report = inspect_config(config=config, vault_arg=vault, env={}, start_dir=tmp_path)

    assert report.templates.files == ["note.md", "project.md"]


def test_template_files_none_when_dir_missing(tmp_path: Path) -> None:
    vault = _mk_vault(tmp_path / "v")
    config = Config(source_path=tmp_path / "absent.yaml")

    report = inspect_config(config=config, vault_arg=vault, env={}, start_dir=tmp_path)

    # dir absent -> None, distinct from [] (present but empty).
    assert report.templates.files is None


def test_ollama_values_from_config_object(tmp_path: Path) -> None:
    config = Config(
        source_path=tmp_path / "absent.yaml",
        ollama=OllamaConfig(base_url="http://host:1", default_model="m", request_timeout_seconds=7),
    )
    report = inspect_config(config=config, env={}, start_dir=tmp_path)

    assert report.ollama.base_url.value == "http://host:1"
    assert report.ollama.request_timeout_seconds.value == 7
