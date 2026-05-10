# Configuration

> **Status:** Phase 1 will implement this. Documented now so the shape
> is visible.

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

# Where run traces go.
run_log_dir: ~/.local/state/para-quest-notes/runs
```

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
   containing both `areas/` and `projects/`, or a configured marker
   file). _(To be implemented in Phase 1.)_
4. `vault:` setting in `config.yaml`
5. Error with a helpful message
