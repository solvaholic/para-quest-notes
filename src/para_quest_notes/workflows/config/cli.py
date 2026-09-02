"""``pqn-config`` CLI entry point.

Read-only inspector for the effective tool config, with provenance. No
LLM, no mutation. Honors the shared ``--vault`` / ``--config`` / ``--format``
flags and adds ``--section`` to isolate one part of the report.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from para_quest_notes.adapter.cli import build_base_parser
from para_quest_notes.adapter.completion import enable_completion
from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import ConfigError

from .contract import (
    SECTIONS,
    ConfigReport,
    ModelsInfo,
    OllamaInfo,
    PathsInfo,
    TemplatesInfo,
    VaultInfo,
)
from .inspect import inspect_config


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-config",
        description=(
            "Report the effective tool configuration a pqn-* run will use, "
            "with provenance (default / config / flag / env). Read-only."
        ),
    )
    p.add_argument(
        "--section",
        choices=SECTIONS,
        default=None,
        help="Report only this section. Default: report everything.",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    enable_completion(parser)
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = inspect_config(config=config, vault_arg=args.vault)

    if args.format == "json":
        print(json.dumps(report.to_dict(args.section), indent=2))
    else:
        _print_text(report, args.section)
    return 0


def _print_text(report: ConfigReport, section: str | None) -> None:
    renderers = {
        "vault": lambda: _render_vault(report.vault),
        "models": lambda: _render_models(report.models),
        "ollama": lambda: _render_ollama(report.ollama),
        "templates": lambda: _render_templates(report.templates),
        "paths": lambda: _render_paths(report.paths),
    }
    if section is None:
        print("# pqn-config")
        for name in SECTIONS:
            print()
            renderers[name]()
    else:
        renderers[section]()


def _prov(source: str) -> str:
    return f"  (source: {source})"


def _render_vault(vault: VaultInfo) -> None:
    print("## vault")
    if vault.resolved:
        print(f"- path: {vault.path}{_prov(str(vault.source))}")
    else:
        print("- path: (unresolved)")
        print(f"- reason: {vault.error}")


def _render_models(models: ModelsInfo) -> None:
    print("## models")
    dm = models.default_model
    print(f"- default_model: {dm.value}{_prov(dm.source)}")
    if models.overrides:
        print("- per-workflow overrides:")
        for o in models.overrides:
            note = "honored" if o.honored else "not honored — not read by the workflow"
            print(f"  - {o.workflow} -> {o.model}  ({note})")
    else:
        print("- per-workflow overrides: none")


def _render_ollama(ollama: OllamaInfo) -> None:
    print("## ollama")
    print(f"- base_url: {ollama.base_url.value}{_prov(ollama.base_url.source)}")
    t = ollama.request_timeout_seconds
    print(f"- request_timeout_seconds: {t.value}{_prov(t.source)}")


def _render_templates(templates: TemplatesInfo) -> None:
    print("## templates")
    td = templates.template_dir
    print(f"- template_dir: {td.value}{_prov(td.source)}")
    if templates.defaults:
        print("- per-type defaults:")
        for ptype, name in sorted(templates.defaults.items()):
            print(f"  - {ptype} -> {name}")
    else:
        print("- per-type defaults: none")
    if templates.files is None:
        print("- files: (vault unresolved or template dir not found)")
    elif templates.files:
        print(f"- files: {', '.join(templates.files)}")
    else:
        print("- files: none found")


def _render_paths(paths: PathsInfo) -> None:
    print("## paths")
    rl = paths.run_log_dir
    print(f"- run_log_dir: {rl.value}{_prov(rl.source)}")
    if paths.config_found:
        print(f"- source_path: {paths.source_path} (found)")
    elif paths.source_path:
        print(f"- source_path: {paths.source_path} (not found — using defaults)")
    else:
        print("- source_path: (using defaults, no file)")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
