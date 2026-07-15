# pqn-config

Report the *effective* tool configuration a `pqn-*` run will use, with
provenance for every value. Read-only. No LLM.

## What it does

Every write workflow has a clear surface, but until now there was no way
to ask "what config will you actually run with?" Agents and scripts had to
*infer* the effective vault, model, and template settings from workflow
output. `pqn-config` answers directly, and for each value reports the
**winning layer** — built-in default, `config.yaml`, an env var, or a
flag — so you (or an agent) can answer "why did it pick that?" without
guessing.

It reports:

- **vault** — the resolved vault path and which discovery rung won
  (`--vault` flag / `PARA_QUEST_VAULT` / cwd walk-up / `config.yaml`), or
  an unresolved marker plus the reason.
- **models** — `ollama.default_model` plus any per-workflow
  `workflows.<name>.model` overrides, each flagged with whether it's
  actually **honored** (see the drift note below).
- **ollama** — `base_url` and `request_timeout_seconds`.
- **templates** — the template dir (`create.template_dir`), the per-type
  defaults (`create.defaults.<type>`), and the template files found in the
  vault.
- **paths** — the effective `run_log_dir` and the `source_path` of the
  loaded config file (or a clear "not found — using defaults").

Unlike the write CLIs, `pqn-config` does **not** fail when no vault is
found. Inspecting config shouldn't require a vault, so an unresolved vault
is reported (`resolved: false` + reason), not raised.

## Usage

```bash
# Full effective config, human-readable (markdown).
pqn-config --vault /tmp/demo-vault

# One section at a time.
pqn-config --vault /tmp/demo-vault --section models
pqn-config --vault /tmp/demo-vault --section templates
pqn-config --vault /tmp/demo-vault --section vault

# JSON for piping or agent wrappers.
pqn-config --vault /tmp/demo-vault --format json | jq
```

`--section` accepts `vault`, `models`, `ollama`, `templates`, or `paths`.
Omit it to report everything. There is deliberately **no** `set`
counterpart — configuration is edited by hand in `config.yaml`.

Vault discovery follows the standard order
([`docs/configuration.md`](../configuration.md)): `--vault` →
`PARA_QUEST_VAULT` → walk up from cwd → `vault:` in `config.yaml`.

Exit codes:

- `0` — report emitted (including when the vault is unresolved).
- `2` — the config file itself is malformed (bad YAML shape).

## Provenance

Each reported value carries a `source`:

- `default` — a built-in constant; no config key set it.
- `config` — a key present in `config.yaml`.
- `env` — an environment variable (vault only: `PARA_QUEST_VAULT`).
- `flag` — a command-line flag (vault only: `--vault`).

The `config` vs `default` distinction is exact: `pqn-config` re-reads the
raw `config.yaml` to see which keys were actually present, rather than
guessing from whether a value happens to equal its default.

## The per-workflow model drift it surfaces

`docs/configuration.md` documents a per-workflow `workflows.<name>.model`
override, but no workflow currently reads it — the LLM workflows resolve
`args.model or config.ollama.default_model` and ignore the per-workflow
key. `pqn-config` makes that visible instead of silent: any
`workflows.<name>.model` you've set is reported with `honored: false`.

If a workflow is later wired to honor its override, add its name to
`_MODEL_OVERRIDE_HONORED` in
`src/para_quest_notes/workflows/config/inspect.py` and it flips to
`honored: true`.

## JSON contract

```json
{
  "vault": {
    "resolved": true,
    "path": "/tmp/demo-vault",
    "source": "flag",
    "error": null
  },
  "models": {
    "default_model": {"value": "granite4.1:30b", "source": "default"},
    "overrides": [
      {"workflow": "ingest", "model": "qwen3:30b", "honored": false}
    ]
  },
  "ollama": {
    "base_url": {"value": "http://localhost:11434", "source": "default"},
    "request_timeout_seconds": {"value": 120, "source": "default"}
  },
  "templates": {
    "template_dir": {"value": "resources/templates", "source": "default"},
    "defaults": {"project": "Project"},
    "files": ["Project.md", "Resource.md"]
  },
  "paths": {
    "run_log_dir": {"value": "/home/u/.local/state/para-quest-notes", "source": "default"},
    "source_path": "/home/u/.config/para-quest-notes/config.yaml",
    "config_found": true
  }
}
```

`--section NAME` narrows the object to just `{"NAME": {...}}`.

Field names are stable across releases — agents and humans both consume
this. New fields may be added; existing fields will not be renamed.

Notes on a couple of fields:

- `templates.files` is `null` when the vault is unresolved or the template
  dir doesn't exist — distinct from `[]` (dir present, no templates).
- `paths.run_log_dir` is the configured base (or the built-in default
  state dir); run traces land in a `runs/` subdirectory of it.

## Scope / non-goals

- **Read-only.** No `set`/write. Edit `config.yaml` by hand.
- **Tool config + resolution only.** Quests are *vault content*, not tool
  config (per the split in [`docs/configuration.md`](../configuration.md)).
  Listing Main/Side Quests belongs to the generated Quest index, not here.
