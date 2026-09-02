# Shell completion

Every `pqn-*` command can complete its own options, its fixed option
values, and — where it makes sense — values read from your vault. Completion
is opt-in: nothing changes until you add an activation snippet to your shell
config.

Bash and native Zsh are both supported. There's nothing to generate, install
into a system directory, or keep in sync by hand: the completions come from
[argcomplete](https://kislyuk.github.io/argcomplete/) reading the same
argparse definitions the commands themselves parse with.

## Activate it

Add this to `~/.bashrc` (Bash) or `~/.zshrc` (Zsh):

```bash
eval "$(register-python-argcomplete pqn-ingest)"
eval "$(register-python-argcomplete pqn-validate)"
eval "$(register-python-argcomplete pqn-create)"
eval "$(register-python-argcomplete pqn-archive)"
eval "$(register-python-argcomplete pqn-daily)"
eval "$(register-python-argcomplete pqn-quests)"
eval "$(register-python-argcomplete pqn-tasks)"
eval "$(register-python-argcomplete pqn-search)"
eval "$(register-python-argcomplete pqn-config)"
eval "$(register-python-argcomplete pqn-eval)"
```

Then restart your shell, or source the file you just edited:

```bash
source ~/.zshrc   # or ~/.bashrc
```

To try it in the current shell only, without editing any dotfile, register a
single command:

```bash
eval "$(register-python-argcomplete pqn-create)"
```

`register-python-argcomplete` ships with argcomplete, which installs
alongside the `pqn-*` commands. If your shell can't find it, the command is
in the same `bin/` directory as `pqn-create` (for a `uv tool install`, that's
usually `~/.local/bin`).

Global argcomplete activation (`activate-global-python-argcomplete`) is not
required. Per-command registration keeps the change scoped to these commands.

## What completes

### Options and fixed values

Every visible option completes, as does every option whose values are a fixed
set:

```bash
pqn-create --type <TAB>
# area  project  resource

pqn-create --quest-kind <TAB>
# main  none  side

pqn-tasks --group-by <TAB>
# area  due  quest

pqn-tasks --date-field <TAB>
# due  scheduled  start

pqn-search --format <TAB>
# json  text
```

`pqn-validate --check` / `--severity` and `pqn-config --section` behave the
same way. Because these values are read off the parser at completion time,
they can never drift from what the command actually accepts.

### Values from your vault

| Argument | Completes to |
| --- | --- |
| `pqn-search --quest`, `pqn-tasks --quest`, `pqn-quests --quest` | Main and Side Quest names |
| `pqn-create --supports` | The same Quests, as `[[Wikilinks]]` |
| `pqn-create --sub-path` | Existing directories under the PARA top-level |
| `pqn-create --template` | Templates in your configured template directory |
| `pqn-daily <target>` | `YYYY-MM-DD` notes in the vault root, `inbox/`, and `resources/daily_notes/` |
| `pqn-archive <target>` | Project notes under `projects/` |

```bash
pqn-search --quest <TAB>
# Health   Home   Stay Sharp

pqn-create --supports <TAB>
# [[Health]]  [[Home]]  [[Stay Sharp]]

pqn-archive <TAB>
# Repaint The Shed   Ship It
```

Names with spaces are quoted for you by the shell — `Stay Sharp` completes
and inserts correctly with no manual escaping.

Targets complete to a bare note name when that name is unique in the vault.
When two notes share a basename, they complete to full vault-relative paths
instead, because a bare name the command can't resolve unambiguously would
just be rejected.

`pqn-create --sub-path` narrows to the matching top-level directory when
`--type` appears earlier on the line:

```bash
pqn-create --type project --sub-path <TAB>   # only directories under projects/
pqn-create --sub-path <TAB>                  # union of projects/, areas/, resources/
```

## How the vault is chosen

Dynamic completion resolves a vault the same way a real run does, using
whatever you've already typed to the left of the cursor:

1. `--vault PATH`, if it's already on the command line
2. `$PARA_QUEST_VAULT`
3. the current directory, walking up to a directory holding `areas/` and
   `projects/`
4. `vault:` in your config

A `--config PATH` you've already typed is honored too, so
`pqn-create --config ./other.yaml --template <TAB>` completes from that
config's template directory. See
[`docs/configuration.md`](configuration.md) for the full resolution rules.

## Behavior and limits

- Completion is **read-only**. It never runs a workflow, writes a run log,
  changes a note, or calls Ollama.
- Completion is **quiet**. If no vault resolves, a directory is missing, or a
  file can't be read, you get no suggestions rather than an error printed
  into your prompt.
- **Static completion always works**, even with no vault in sight. Option
  names and fixed values need nothing from disk.
- The deprecated `pqn-create --quest` alias is hidden from completion. Use
  `--quest-kind`.
- `pqn-create --supports` completes wikilinks because that's the syntax the
  flag accepts today.

## Troubleshooting

**Nothing happens when I press Tab.**
Check that the registration actually ran: `complete -p pqn-create` (Bash) or
`echo $_comps[pqn-create]` (Zsh) should print something. If it doesn't, you
probably haven't restarted or sourced your shell config since editing it.

**`register-python-argcomplete: command not found`.**
It lives beside the `pqn-*` commands. Confirm with
`ls "$(dirname "$(command -v pqn-create)")" | grep argcomplete` and add that
directory to your `PATH` if it's missing.

**Options complete but vault values don't.**
The vault isn't resolving. Run `pqn-config --section vault` from the same
directory to see which rung of the ladder wins, if any.

**Zsh completes but shows escaped names.**
Make sure you're using native Zsh completion (`compinit` loaded) rather than
`bashcompinit`. The snippet above works with the native system.

**Completion feels slow in a very large vault.**
Vault-derived candidates walk the relevant directories on each Tab. Narrowing
first (`pqn-archive Rep<TAB>`) does the same work; if it's a persistent
problem, please open an issue with a rough note count.
