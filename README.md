# para-quest-notes

Local, scripted workflows for managing markdown notes organized by
**PARA + Quest**, powered by small LLMs running locally via
[Ollama](https://ollama.com/).

> **Status:** pre-alpha. The architecture, CLI surface, and notes-system
> spec are still settling. Project name is provisional.

## Why

Most "AI for notes" tools require sending your notes to someone else's
servers. This one doesn't. Workflows do as much as possible with plain
Python, and only call a local LLM for the bits that genuinely need
natural-language judgment (classification, summarization, escalation
when rules don't fit).

The PARA + Quest organization model (see
[`docs/notes-system.md`](docs/notes-system.md)) is the value
proposition: it lets you align day-to-day work with long-term goals.
The workflows preserve that reasoning, locally.

## Design principles

1. **Local first.** No cloud LLM calls. Notes never leave your machine.
2. **Scripts are the brains.** LLMs only do what scripts can't: judgment
   calls and natural-language summarization.
3. **Small models welcome.** Targeted at models that fit on a laptop
   (Granite 4, Gemma 3, Qwen 3, Phi-4 reasoning, etc.).
4. **CLI first, agent-friendly.** Every workflow is a CLI you can pipe
   and cron. Structured JSON output is a first-class citizen, so an
   agent can wrap a workflow without ever seeing your note bodies.
5. **Bring your own vault.** Install once with `pipx`/`uv tool install`,
   then run against any vault on disk.

## Status / roadmap

- [x] Phase 0: repo bootstrap
- [x] Phase 1: thin runtime adapter (Ollama client, Step/Workflow,
      escalation, config + vault discovery)
- [x] Phase 2: synthetic corpus generator (also serves as demo vault —
      see [`docs/corpus.md`](docs/corpus.md) and
      [`samples/vault/`](samples/vault/))
- [ ] Phase 3: pilot workflow - `pqn-ingest` (inbox → PARA + Quest)
- [ ] Phase 4: per-step eval harness (matrix over models / prompts)
- [ ] Phase 5: translate remaining workflows (`validate`, `create`,
      `archive`, `daily`)
- [ ] Phase 6: polish + v0.1 release
- [ ] Phase 7 (deferred): agent SKILL.md wrappers

## Try the sample vault

A small (~30-note) sample vault lives at
[`samples/vault/`](samples/vault/) for poking at the workflows
without involving any real notes:

```bash
uv sync --dev

# Inspect the committed sample vault
ls samples/vault/

# Or generate a fresh one with different seed/options
uv run python -m para_quest_notes.corpus \
    --out ./demo-vault --seed 42 --projects 8 --inbox 6 --daily 14
```

See [`docs/corpus.md`](docs/corpus.md) for the full shape taxonomy.

## Install (eventually)

```bash
# Once v0.1 is out:
uv tool install para-quest-notes
# or
pipx install para-quest-notes
```

For now, clone and use `uv`:

```bash
git clone https://github.com/solvaholic/para-quest-notes.git
cd para-quest-notes
uv sync --dev
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).
