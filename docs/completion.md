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

Registration is done by `register-python-argcomplete`, a small script that
ships with argcomplete. **Whether that script is on your `PATH` depends on how
you installed `para-quest-notes`:**

| Install method | `register-python-argcomplete` on `PATH`? |
| --- | --- |
| `uv tool install` / `pipx install` | **No** - it stays inside the tool's private venv |
| `pip install` / `uv pip install` into an active venv | Yes |

`uv tool` and `pipx` deliberately expose only the entry points of the package
you named. The `pqn-*` commands get linked into `~/.local/bin`; argcomplete's
own script does not, even though argcomplete is installed.

The snippet below covers both cases by resolving the script next to the real
`pqn-create`. Add it to `~/.bashrc` (Bash) or `~/.zshrc` (Zsh):

```bash
PQN_BIN="$(dirname "$(readlink -f "$(command -v pqn-create)")")"
for cmd in ingest validate create archive daily quests tasks search config eval; do
  eval "$("$PQN_BIN/register-python-argcomplete" "pqn-$cmd")"
done
```

Then restart your shell, or source the file you just edited:

```bash
source ~/.zshrc   # or ~/.bashrc
```

To try it in the current shell only, without editing any dotfile, register a
single command:

```bash
eval "$("$(dirname "$(readlink -f "$(command -v pqn-create)")")/register-python-argcomplete" pqn-create)"
```

If you'd rather keep the snippet short, install argcomplete as a tool in its
own right so its script lands on your `PATH` too:

```bash
uv tool install argcomplete   # or: pipx install argcomplete
```

With that in place, plain `eval "$(register-python-argcomplete pqn-create)"`
works and you can drop the `PQN_BIN` lookup.

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
Expected after a `uv tool install` or `pipx install` - those don't put
argcomplete's script on your `PATH`. Use the `PQN_BIN` form from
[Activate it](#activate-it), or install argcomplete as its own tool. To see
where the script actually is:

```bash
ls "$(dirname "$(readlink -f "$(command -v pqn-create)")")" | grep argcomplete
```

**`readlink: illegal option -- f`.**
Only on macOS older than 12.3, whose `readlink` predates `-f`. Find the
directory without it - `ls -l "$(command -v pqn-create)"` prints the symlink
target - then use that directory literally in place of `$PQN_BIN`. For a `uv
tool install` it's `~/.local/share/uv/tools/para-quest-notes/bin`.

**Neither `register-python-argcomplete` nor argcomplete is anywhere in the
tool venv.**
Your installed version predates shell completion, so argcomplete was never
pulled in as a dependency. Check what you have with
`uv tool list | grep para-quest-notes` (or `pipx list`), and reinstall from a
revision that includes it:

```bash
uv tool install --force git+https://github.com/solvaholic/para-quest-notes@main
```

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
