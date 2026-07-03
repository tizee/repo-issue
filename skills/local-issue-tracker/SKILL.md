---
name: local-issue-tracker
description: Track bugs, features, and UI regressions as repo-local markdown tickets using the `issue` CLI (repo-issue). Use this skill whenever the user wants to file a bug, log a feature request, track a TODO that deserves a ticket, list or search existing issues, check issue status, resolve or close tickets, or set up issue tracking in a repository. Also use it when the user mentions "issue tracker", "ticket", "BUG-001"-style IDs, an `issues/` directory, or asks "what's open", "what am I working on", or "file this as an issue" — even if they don't name the tool. Prefer this over GitHub issues when the repo has an `issues/` directory.
---

# Local Issue Tracker (`issue` CLI)

Manage repo-local issue tickets with the globally installed `issue` command.
Tickets are plain markdown files with YAML frontmatter stored inside the
repository — no server, no database. The CLI discovers the `issues/` data
directory by walking up from the current working directory (the same way git
finds `.git/`), so commands work from anywhere inside the repo.

## When the data directory is missing

Every command except `init` fails fast if no `issues/` directory exists
upstream. If that happens, ask the user whether to initialize tracking, then
run `issue init` from the repo root. Don't silently init in repos that may
intentionally not use this tool.

## Data model

```
issues/
├── templates/       # Editable per-repo issue templates
├── active/          # open + in_progress tickets (one .md per ticket)
├── resolved/        # resolved + cancelled tickets
└── counters.json    # Per-prefix ID counters (BUG, FEAT, UI, ...)
```

Each ticket is `<PREFIX>-<NNN>.md` (e.g., `BUG-001.md`) with frontmatter
fields: `id`, `title`, `created`, `status`, `author`, `type`, `priority`,
`labels`, `blocked_by`, `related` — followed by structured markdown sections.

| Status | Lives in | Meaning |
|--------|----------|---------|
| `open` | `active/` | Newly created |
| `in_progress` | `active/` | Being worked on |
| `resolved` | `resolved/` | Completed |
| `cancelled` | `resolved/` | No longer relevant |

`issue update` moves the file between `active/` and `resolved/` automatically.
Never move ticket files between these directories by hand within a repo — let
the CLI keep status and location consistent. (Moving tickets *between repos*
with `mv` is fine; IDs are preserved and the allocator skips taken numbers.)

## Command reference

```bash
issue init                            # Scaffold issues/ in current directory
issue list                            # Active issues (sorted by priority)
issue list bug open                   # Filter: type + status shorthand
issue list priority:p0 label:render   # Filter: explicit key:value
issue list --all --json               # All issues (active+resolved) as JSON
issue list --labels                   # All labels with counts
issue create <type> "<title>"         # type: bug | feat | ui
issue create bug "Crash on save" -d "Repro details" -p p0 -a username
issue create bug "Crash on save" --description-file notes.md
issue template bug                    # Print fillable body skeleton
issue create bug "Crash on save" --body-file body.md --json
issue update BUG-001 in_progress      # open|in_progress|resolved|cancelled
issue show FEAT-030                   # Full ticket content
issue show FEAT-030 --json            # Frontmatter + body, as JSON
issue search "null pointer" --all     # Case-insensitive full-text search
issue stats [--json]                  # Counts by type/status/priority + blocked
issue reconcile                       # Verify file/counter consistency
```

Create options: `-p/--priority` (p0=critical, p1=high, p2=medium, p3=low;
default p2), `-a/--author` (default `agent` — pass the user's name when
filing on their behalf if known), `--json` (machine-readable result with
`id` and `file`), and exactly one content channel:

| Channel | Effect |
|---------|--------|
| `-d "text"` / `-d -` (stdin) | Body becomes a single `## Summary` section |
| `--description-file PATH` (`-` = stdin) | Same, loaded from a file |
| `--body-file PATH` (`-` = stdin) | Your markdown replaces the whole body |
| none | Full template skeleton kept for later editing |

Frontmatter (`id`, `status`, dates, `type`) is always tool-owned — a body
that starts with its own `---` block is rejected.

List filters combine with AND: bare words `bug|feat|ui` match type,
`open|in_progress|resolved|cancelled` match status; `type:`, `status:`,
`priority:`, `label:` prefixes are explicit (label matches substrings).

## Working with tickets as an agent

**Prefer `--json` everywhere.** All read commands (`list`, `search`, `show`,
`stats`) and both write commands (`create`, `update`) support `--json`.
Write results include the ticket `id` and `file` path for follow-up steps.
Use plain output only when relaying directly to the user.

**Never pass long text inline.** Multi-line descriptions with quotes,
backticks, or `$(...)` break shell quoting when inlined into `-d "..."`.
Pipe them instead:

```bash
printf '%s\n' "long multi-line text" | issue create bug "Title" -d -
issue create bug "Title" --description-file /tmp/notes.md
```

**Creating a good ticket** — pick the channel that matches how much you have
to say:

- *Quick capture* (a sentence or two): `-d` / `-d -`. The ticket body is a
  clean Summary section — no placeholder skeleton to clean up afterwards.
- *Structured report* (repro steps, expected/actual, impact): get the
  skeleton with `issue template <type>`, fill in the sections that apply,
  delete the ones that don't, and submit in one step:

  ```bash
  issue template bug > /tmp/body.md   # fill it in, then:
  issue create bug "Concise searchable title" --body-file /tmp/body.md --json
  ```

  Writing the body yourself and passing `--body-file` is the preferred way
  to produce a complete ticket — never leave `<!-- ... -->` placeholder
  comments in a submitted body.

Choose the type by intent: `bug` for incorrect behavior, `feat` for new
capability or enhancement, `ui` for visual/rendering regressions.

**Updating non-status fields** (priority after creation, labels,
`blocked_by`, body sections): edit the markdown file directly — the CLI
manages status transitions, ID allocation, and creation-time priority
(`-p`). `create --json` and `update --json` return the file path; `list`
and `search` JSON omit it, so locate files by convention
(`issues/{active,resolved}/<ID>.md`).

**Resolving work**: when you fix something tracked by a ticket, ask or
confirm before running `issue update <ID> resolved`. Consider appending a
short resolution note to the ticket body first so the resolved ticket
documents what was done.

**Dependencies**: `blocked_by: ["FEAT-002"]` in frontmatter marks blockers.
`issue stats` lists blocked issues. There is no automatic unblocking — when
resolving a ticket, check whether other tickets list it in `blocked_by` and
mention them to the user (`issue search "<ID>"` finds references).

**Triage queries** map naturally:
- "What's open?" → `issue list --json`
- "What am I working on?" → `issue list in_progress --json`
- "Anything critical?" → `issue list priority:p0 --json`
- "Did we already file this?" → `issue search "<keywords>" --all --json`
  (always search before creating to avoid duplicates)

## Health checks

If listing looks wrong or IDs seem off, run `issue reconcile`. It reports
mismatched frontmatter IDs, misplaced files (resolved status sitting in
`active/`), orphan filenames, and counter problems. Fix what it reports
manually, then re-run until it prints `OK`.

## Example: filing a bug from a conversation

User says: "the export command crashes when the path has spaces, can you file that?"

```bash
issue search "export" --all --json          # 1. Check for duplicates
issue template bug > /tmp/body.md           # 2. Get the skeleton
# 3. Fill body.md from conversation context: Summary, Steps to Reproduce
#    ('app export /tmp/my dir/out.csv'), Expected/Actual Behavior, Impact.
#    Delete sections that don't apply.
issue create bug "Export crashes on paths with spaces" \
  --body-file /tmp/body.md -p p1 --json
# -> {"id": "BUG-007", ..., "file": "/repo/issues/active/BUG-007.md"}
```

Confirm to the user: "Filed BUG-007: Export crashes on paths with spaces (p1)."
