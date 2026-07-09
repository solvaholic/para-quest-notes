# Body Templates

User-defined body templates for `pqn-create`. Templates live in the
vault and provide custom note structure when the built-in skeletons
don't fit.

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
| `$quest` | Quest kind: `main`, `side`, or `none` |
| `$supports` | Comma-separated supports list (e.g., `[[Health]], [[Work]]`) |
| `$source_url` | Source URL if provided, empty string otherwise |
| `$created` | ISO date (e.g., `2026-07-09`) |

### Escaping

Variables are expanded everywhere in the template, including inside
code fences. To include a literal `$` followed by a variable name,
double it:

```
$$title    renders as    $title
$$created  renders as    $created
```

Unknown `$variables` (anything not in the table above) are left as-is.
So `$PATH` or `$HOME` in a shell example won't be touched.

## Priority

When multiple body sources are available, priority is:

1. **stdin** (`--body-stdin`) - always wins
2. **explicit `--template`** - flag on this invocation
3. **config default** - per-type default from `config.yaml`
4. **built-in skeleton** - type-appropriate minimal structure

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

Produces a note with canonical frontmatter prepended and the template
body (with `$title` and `$created` substituted).

## Fallback behavior

If a named template isn't found, `pqn-create` falls back to the
built-in skeleton (no error, no escalation). The JSON output includes
a `body_source` field indicating what was used:

- `"template:<name>"` - template was found and rendered
- `"skeleton"` - built-in skeleton (no template found or none specified)
- `"skeleton (template not found)"` - template specified but missing
- `"stdin"` - body came from stdin

## Future: whole-note templates (#75)

Currently templates provide body content only. A planned evolution
will let templates include frontmatter that merges under the generated
values (generated wins on conflict, template provides supplemental
keys like `status: draft`). See #75.
