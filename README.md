# repo-issue

Repo-local issue ticket tracker. Tickets are markdown files with YAML
frontmatter, stored inside the repository they belong to — no server, no
database, no runtime dependencies. One globally installed `issue` command
serves any number of repos.

Extracted from [llm.tizee](../llm.tizee) where it started as in-repo tooling
(FEAT-404).

## Install

```bash
uv tool install --from /path/to/issue.tizee repo-issue
```

## Data model

Each repo owns its ticket data in an `issues/` directory:

```
issues/
├── templates/       # Issue templates (bug_report, feature_request, ui_regression)
├── active/          # Open / in-progress issues
├── resolved/        # Resolved / cancelled issues
└── counters.json    # Per-prefix ID counters
```

The `issue` command discovers this directory by walking up from the current
working directory (like `git` finds `.git/`). If none is found, it fails fast
and suggests `issue init`.

## Usage

```bash
issue init                            # Scaffold issues/ in the current repo
issue list                            # List active issues
issue list bug open                   # Filter by type and status
issue list priority:p0                # Filter by priority
issue list --all --json               # All issues as JSON
issue create bug "Fix crash" -p p0    # Create issue
issue update BUG-001 resolved         # Update status (moves file)
issue show FEAT-030                   # Show issue details
issue show FEAT-030 --json            # Frontmatter + body as JSON
issue search "null pointer" --all     # Full-text search
issue stats                           # Summary counts
issue reconcile                       # Check file/counter consistency
```

## Writing issue content

Three content channels for `create`, designed so that long or structured
text never has to be escaped through the shell:

```bash
# Quick capture: short summary inline (body becomes a single Summary section)
issue create bug "Fix crash" -d "Crash when saving with unicode filenames"

# Long description: from a file or stdin -- no shell quoting pitfalls
issue create bug "Fix crash" --description-file notes.md
git log -1 --format=%B | issue create bug "Fix crash" -d -

# Full structured ticket: get the template skeleton, fill it, pass it back
issue template bug > body.md          # print fillable body sections
issue create bug "Fix crash" --body-file body.md --json
```

Frontmatter (id, dates, status, type) is always tool-owned; a body that
carries its own `---` frontmatter block is rejected.

`--json` on `create` and `update` emits machine-readable results
(`{"id": ..., "status": ..., "file": ...}`) for scripted workflows.

## Issue lifecycle

| Status | Location | Meaning |
|--------|----------|---------|
| `open` | `active/` | Newly created |
| `in_progress` | `active/` | Being worked on |
| `resolved` | `resolved/` | Completed |
| `cancelled` | `resolved/` | No longer relevant |

## Moving tickets between repos

Ticket files are plain markdown — move them with `mv`. IDs are preserved:
the ID allocator skips numbers already taken by existing files (in both
`active/` and `resolved/`), so imported tickets never collide with new ones
even when the destination repo's counter is behind.
