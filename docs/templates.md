# Note Templates

User-defined whole-note templates and deterministic body placeholders for `pqn-create` and missing-note creation in `pqn-daily`. Templates live in the vault and can provide supplemental frontmatter plus custom note structure when built-in skeletons do not fit. Both workflows share one parser, renderer, path resolver, missing-template fallback, and atomic new-file publication substrate; each workflow supplies its own metadata authority, variables, destination, and fallback skeleton. Bodies supplied through `pqn-create --body-stdin` use the same placeholder renderer with create's variable mapping.

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
pqn-daily --date 2026-09-02 --create-missing --template daily
```

Filenames can use any valid identifier style (kebab-case, snake_case,
Title Case - all work).

## `pqn-create` variables

Template bodies and non-empty `--body-stdin` bodies use `$variable` syntax. Values come from the final normalized create inputs after deterministic Quest and supports resolution. Available variables:

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

## `pqn-daily` variables

Daily template values come from the selected date, not wall-clock execution time:

| Variable | Value |
|----------|-------|
| `$title` | Selected ISO date, for compatibility with title-oriented templates |
| `$date` | Selected ISO date |
| `$created` | Selected ISO date, so create-oriented date templates remain reusable |
| `$year` | Four-digit selected year |
| `$month` | Two-digit selected month |
| `$day` | Two-digit selected day |

Create-only variables such as `$type`, `$quest_kind`, and `$supports` are not assigned for daily notes, so safe substitution leaves those tokens unchanged.

### Escaping

Variables are expanded everywhere in template and stdin bodies, including inside code fences. Template frontmatter is parsed as YAML and is not variable-substituted; stdin is never parsed as template metadata. To include a literal `$`, double it:

```
$$title    renders as    $title
$$created  renders as    $created
```

Unknown `$variables` (anything not in the table above) are left as-is, so `$PATH` or `$HOME` in a shell example will not be touched.

## Frontmatter

A template may start with YAML frontmatter. Both workflows parse it separately from the body, so placeholders in frontmatter are never rendered. Both tolerate legacy tail backmatter, merge it beneath leading frontmatter, migrate it into one frontmatter block on write, and leave malformed or non-mapping metadata fences as literal body text.

`pqn-create` merges template metadata under its generated metadata, then emits one canonical frontmatter block. Generated and CLI-derived values always win on conflicts:

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

`pqn-daily` retains template-supplied metadata but does not synthesize `type`, `quest-kind`, `supports`, `source_url`, `created`, or any other PARA metadata. Daily notes continue to inherit Quest context from their contents. After rendering the body, daily preserves a custom first ATX H1 or prepends `# YYYY-MM-DD` when the first nonblank body line is not an H1.

## Priority

For `pqn-create`, priority is:

1. **stdin** (`--body-stdin`) - always wins
2. **explicit `--template`** - flag on this invocation
3. **config default** - per-type default from `config.yaml`
4. **built-in skeleton** - type-appropriate minimal structure

When non-empty stdin wins, the template is not loaded, so neither its body nor its supplemental frontmatter is applied. The stdin body is rendered with the same known variables, `$$` escaping, and unknown-token pass-through as a template body. Frontmatter-looking text from stdin remains body text. Empty or whitespace-only stdin retains the existing fallback behavior and continues to the selected template or built-in skeleton.

For `pqn-daily`, priority is:

1. **explicit `--template`**
2. **explicit `--no-template`**
3. **`workflows.daily.template`**
4. **built-in H1-only skeleton**

Daily template selection affects only a missing-note creation branch. It never merges into or rewrites an existing daily note, does not enable `create_missing`, and does not bypass `--apply`. A dry-run still resolves, loads, parses, and renders the selected template before reporting the plan.

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

Set one nullable default for missing daily notes while continuing to use the create template directory:

```yaml
workflows:
  create:
    template_dir: resources/templates
  daily:
    template: daily
```

An explicit daily `--template` overrides this value; `--no-template` bypasses it and uses the H1-only skeleton.

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

If a named template isn't found, both workflows fall back to their built-in skeleton (no error, no escalation). The JSON plan includes a `body_source` field indicating what was used:

- `"template:<name>"` - template was found and rendered
- `"skeleton"` - built-in skeleton (no template found or none specified)
- `"skeleton (template not found)"` - template specified but missing
- `"stdin"` - body came from stdin and known placeholders were rendered

`"stdin"` applies only to `pqn-create`. For `pqn-daily`, `body_source` is null when the selected note already exists because no missing-note body was composed.
