# Configuration

## Tool config (in your home directory)

Tool settings live at:

```
$XDG_CONFIG_HOME/para-quest-notes/config.yaml
# falls back to:
$HOME/.config/para-quest-notes/config.yaml
```

Empty file is fine - sensible defaults apply. Example:

```yaml
# Default vault if --vault is not given and cwd discovery fails.
vault: ~/notes

# Ollama endpoint and default model.
ollama:
  base_url: http://localhost:11434
  default_model: granite4.1:30b
  request_timeout_seconds: 120

# Per-workflow overrides.
workflows:
  ingest:
    model: qwen3:30b
    temperature: 0.2
    dry_run: true   # require --apply to actually move files
  tasks:
    # Effective-date precedence; omitted fields are ignored.
    date_fields: [scheduled, due, start]
  daily:
    # Safe defaults: neither setting bypasses the --apply write gate.
    create_missing: false
    open_existing: false
    # An argv list, not a shell command string. The note path is appended.
    editor:
      - code
      - --reuse-window

# Where run traces go.
run_log_dir: ~/.local/state/para-quest-notes/runs
```

`pqn-tasks` resolves its date fields as `--date-field` flags, then `workflows.tasks.date_fields`, then the built-in `[due, scheduled, start]` default. The configured value must be a non-empty list containing only `due`, `scheduled`, and `start`.

`pqn-daily` resolves `create_missing` and `open_existing` from explicit positive or negative CLI flags, then `workflows.daily`, then the safe `false` defaults. `create_missing` still requires `--apply` before it writes. `editor` must be a non-empty argv list of non-empty strings; the resolved note path is appended and the process runs without a shell. There is no default editor or OS-specific discovery.

## Vault content (in your vault)

Anything that's part of your notes lives in your vault, not in tool
config:

- Quest outline (Main + Side Quest notes in `areas/`)
- Capability notes (also in `areas/`, with `capability: true` in
  backmatter)
- Routine definitions (sections inside Area notes)

This way your "what matters to me" can move with your vault, while
"what model and prompts to use" stays per-machine.

## Vault discovery

In order, the workflows resolve the vault path as:

1. `--vault PATH` argument
2. `PARA_QUEST_VAULT` environment variable
3. Walk up from `cwd` looking for a vault marker (a directory
   containing both `areas/` and `projects/`).
4. `vault:` setting in `config.yaml`
5. Error with a helpful message

## Inspecting the effective config

To see the config a `pqn-*` run will actually use - and where each value
came from (default / `config.yaml` / env / flag), plus which
vault-discovery rung won - run the read-only inspector:

```bash
pqn-config                    # full effective config
pqn-config --section models   # just the models section
pqn-config --format json      # for piping / agent wrappers
```

See [`docs/workflows/config.md`](workflows/config.md) for the full output
shape and the JSON contract.
