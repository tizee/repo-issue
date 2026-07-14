# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Build, test, lint

```bash
# Run all tests
uv run pytest

# Run a single test file or specific test
uv run pytest tests/test_cli.py
uv run pytest tests/test_cli.py::TestCreateCommand::test_create_bug_issue

# Lint / format
uv run ruff check .
uv run ruff format .

# Install as globally available CLI (for real-world testing)
uv tool install --from . repo-issue
```

The project has zero runtime dependencies and only `pytest` + `ruff` as dev dependencies. `uv` manages the virtualenv in `.venv/`.

## Architecture

This is a **zero-dependency Python CLI** (`issue` command) that manages repo-local issue tickets as markdown files with YAML frontmatter — no server, no database. Each repo owns its `issues/` directory.

### Core design decisions

**Directory discovery.** `discovery.find_issues_dir()` walks up from cwd (like git finds `.git/`). The CLI is installed globally but operates on per-repo data. Fails fast with a clear hint if no `issues/` directory exists. `init` is the only command that doesn't require an existing data directory.

**File-based data model.** Tickets live as `<PREFIX>-<NNN>.md` files in `active/` or `resolved/`. Status transitions (`open`/`in_progress` → `resolved`/`cancelled`) move files between these directories. Frontmatter is always tool-owned; user/agent-provided content goes in the markdown body.

**Content channels (mutually exclusive).** `create_issue.py` supports three body modes:
- `-d TEXT` / `-d -` — short summary → `## Summary` section only
- `--body-file PATH` / `-` — full markdown body (rejected if it starts with `---`)
- Neither — template skeleton kept for later manual editing

**Line-level frontmatter editing.** `yaml_utils.set_frontmatter_field()` edits individual frontmatter lines by matching key prefixes, avoiding a full parse/dump round-trip. This means fields the simple YAML parser can't model (comments, exotic values) survive byte-for-byte.

**Simple YAML parser.** `yaml_utils._parse_yaml_block()` is a hand-rolled parser supporting key-value pairs, inline lists (`[a, b]`), and multi-line lists (`- item`). It cannot handle nested structures — this is intentional; frontmatter is kept flat.

**ID allocation with collision skip.** `create_issue.get_next_id()` uses `counters.json` with `fcntl.flock()` for atomicity, with a fallback to directory scan. Numbers already taken by existing files are skipped — this lets tickets imported from other repos keep their original IDs without renumbering.

**Color output.** `cli.should_disable_color()` respects `NO_COLOR` env var and non-TTY stdout. All human-readable output uses this.

**JSON everywhere.** All read commands (`list`, `search`, `show`, `stats`) and write commands (`create`, `update`) support `--json` for machine-readable output.

### Key files

| File | Role |
|------|------|
| `issue_tracker/cli.py` | Argument parsing, command dispatch, output formatting. The main entry point. |
| `issue_tracker/discovery.py` | Finds `issues/` directory by walking up from cwd. |
| `issue_tracker/init.py` | Scaffolds `issues/` with bundled templates, `counters.json`, and directory layout. |
| `issue_tracker/create_issue.py` | Issue creation: ID allocation (atomic counter + file locking), template substitution, content channel logic. |
| `issue_tracker/update_status.py` | Status transitions: edits frontmatter lines in-place, moves files between `active/` and `resolved/`. |
| `issue_tracker/yaml_utils.py` | Simple YAML frontmatter parse/dump, plus line-level field editing. |
| `issue_tracker/templates/` | Bundled `.md` templates with `{{PLACEHOLDER}}` variables. Copied to `issues/templates/` on `init`. |
| `skills/local-issue-tracker/SKILL.md` | AI agent skill definition for consuming the `issue` CLI. |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Operation error (not found, no issues dir, consistency problems) |
| 2 | Usage error (invalid arguments) |

### Testing conventions

Tests use `pytest` with fixtures that create temporary `issues/` directory structures. The CLI is tested by patching `find_issues_dir` to return a temp directory and `sys.argv` to simulate command-line invocation. Output is captured via `capsys`. Command handler functions (`cmd_list`, `cmd_create`, etc.) are testable directly via `dispatch_command`.
