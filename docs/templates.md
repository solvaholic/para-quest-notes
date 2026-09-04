# Note Templates

User-defined whole-note templates for `pqn-create`. Templates live in the
vault and can provide supplemental frontmatter plus custom note structure
when the generated metadata and built-in skeletons don't fit.

## Where templates live

Default location: `<vault>/resources/templates/<name>.md`

Configurable via `config.yaml`:

```yaml
workflows:
  create:
    template_dir: resources/templates  # vault-relative
```

Templates are excluded from `pqn-validate` checks (they're
infrastructure, not PARA notes).

## Naming

Reference templates by name (without `.md`) or by vault-relative path:

```bash
pqn-create --template weekly-review ...        # looks up resources/templates/weekly-review.md
pqn-create --template my/custom/template.md ...  # vault-relative path
```

Filenames can use any valid identifier style (kebab-case, snake_case,
Title Case - all work).

## Variables

Templates use `$variable` syntax. Available variables:

| Variable | Value |
|----------|-------|
| `$title` | The note title (from `--title` or path inference) |
| `$type` | PARA type: `project`, `area`, or `resource` |
| `$quest_kind` | Quest kind: `main`, `side`, or `none` |
| `$supports` | Comma-separated supports list (e.g., `[[Health]], [[Work]]`) |
| `$source_url` | Source URL if provided, empty string otherwise |
| `$created` | ISO date (e.g., `2026-07-09`) |

`$quest` is a deprecated alias for `$quest_kind`, kept so templates
written before the [#98](https://github.com/solvaholic/para-quest-notes/issues/98)
rename keep working. Prefer `$quest_kind` in new templates; `$quest` is
slated for removal at v1.0. (The variable can't be named `$quest-kind`:
`string.Template` names allow only letters, digits, and underscores, so a
hyphen would be read as `$quest` followed by literal `-kind`.)

### Escaping

Variables are expanded everywhere in the template body, including inside code
fences. Template frontmatter is parsed as YAML and is not variable-substituted.
To include a literal `$` followed by a variable name, double it:

```
$$title    renders as    $title
$$created  renders as    $created
```

Unknown `$variables` (anything not in the table above) are left as-is.
So `$PATH` or `$HOME` in a shell example won't be touched.

## Frontmatter

A template may start with YAML frontmatter. `pqn-create` merges template
metadata under its generated metadata, then emits one canonical frontmatter
block. Generated and CLI-derived values always win on conflicts:

- `type`
- `quest-kind`
- `supports`
- `source_url` (from `--source-url`)
- `created`

This precedence includes generated omissions. For example, template
`supports` or `source_url` values are removed when the resolved create inputs
do not provide those fields. Templates are for supplemental metadata, not
defaults for generated fields.

Supplemental mappings, lists, booleans, numbers, and strings are preserved.
Null-valued keys are omitted by the canonical frontmatter serializer. Known
keys appear in canonical order, followed by supplemental keys in template
order.

The canonical Quest classifier is `quest-kind`. A legacy template `quest` key
is tolerated and migrated on write, but it never overrides the generated
`quest-kind` value.

Legacy tail backmatter is also tolerated and migrated into the generated
frontmatter. When both template frontmatter and backmatter define a
supplemental key, frontmatter wins. A malformed YAML fence or a YAML value that
is not a mapping is not interpreted as metadata; it remains literal template
body text, matching the vault parser's existing read policy.

## Priority

When multiple body sources are available, priority is:

1. **stdin** (`--body-stdin`) - always wins
2. **explicit `--template`** - flag on this invocation
3. **config default** - per-type default from `config.yaml`
4. **built-in skeleton** - type-appropriate minimal structure

When stdin wins, the template is not loaded, so neither its body nor its
supplemental frontmatter is applied. Stdin remains verbatim; rendering
placeholders in stdin is tracked separately in #110.

## Config defaults

Set a default template per PARA type so `--template` isn't needed
every time:

```yaml
workflows:
  create:
    template_dir: resources/templates
    defaults:
      project: weekly-review    # auto-applies when --type project
      area: null                # no default (uses built-in skeleton)
      resource: reference       # auto-applies when --type resource
```

An explicit `--template` flag overrides the config default.

## Example template

`<vault>/resources/templates/weekly-review.md`:

```markdown
---
status: draft
review_cycle: weekly
---
# $title

## Week of $created

### What went well

-

### What to improve

-

### Next week's focus

-
```

Usage:

```bash
pqn-create --type project --title "Weekly Review" \
  --supports "[[Work]]" --template weekly-review --apply
```

Produces a note with generated canonical frontmatter, then the template's
supplemental `status` and `review_cycle` keys, followed by the template body
with `$title` and `$created` substituted.

## Fallback behavior

If a named template isn't found, `pqn-create` falls back to the
built-in skeleton (no error, no escalation). The JSON output includes
a `body_source` field indicating what was used:

- `"template:<name>"` - template was found and rendered
- `"skeleton"` - built-in skeleton (no template found or none specified)
- `"skeleton (template not found)"` - template specified but missing
- `"stdin"` - body came from stdin
