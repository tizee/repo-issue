"""Unified issue management CLI.

Usage:
    issue init
    issue list [filters...] [--resolved] [--all] [--json] [--labels]
    issue create <type> <title> [options]
    issue update <issue-id> <status> [--json]
    issue show <issue-id> [--json]
    issue template <type>
    issue search <query>
    issue stats
    issue reconcile

Commands:
    init        Scaffold issues/ directory in the current repo
    list        List and filter issue tickets
    create      Create a new issue from template
    update      Update issue status and manage lifecycle
    show        Display full issue details
    template    Print a template body skeleton for filling in
    search      Full-text search across all issues
    stats       Show summary statistics
    reconcile   Check consistency between files and counters

The issues/ data directory is discovered by walking up from the current
working directory (like git finds .git/).

Examples:
    issue init                          # Scaffold issues/ in current repo
    issue list                          # List all active issues
    issue list bug open                 # Filter by type and status
    issue list --resolved               # Include resolved issues
    issue list --all                    # Show all issues (active + resolved)
    issue list --json                   # Machine-readable JSON output
    issue list priority:p0              # Filter by priority
    issue list --labels                 # List all labels
    issue create bug "Fix crash"        # Create bug report
    issue create feat "New feature" -d "Description" -p p1
    issue create bug "Crash" -d -       # Read description from stdin
    issue create bug "Crash" --description-file notes.md
    issue template bug > body.md        # Get skeleton, fill it in, then:
    issue create bug "Crash" --body-file body.md
    issue update BUG-001 resolved       # Mark as resolved
    issue show FEAT-030                 # Show issue details
    issue show FEAT-030 --json          # Show as JSON (frontmatter + body)
    issue search "null pointer"         # Full-text search
    issue stats                         # Summary counts
    issue reconcile                     # Check file/counter consistency
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from .create_issue import IssueCreationError, create_issue
from .discovery import IssuesDirNotFoundError, find_issues_dir
from .init import IssuesInitError, init_issues_dir
from .update_status import IssueUpdateError, update_issue_status
from .yaml_utils import parse_yaml_frontmatter, split_frontmatter_raw


def should_disable_color() -> bool:
    """Auto-detect whether color output should be disabled.

    Checks:
    1. NO_COLOR env var (no-color.org standard) - presence disables color
    2. stdout not a TTY (piped/redirected)

    Returns:
        True if color should be disabled, False otherwise.
    """
    if os.environ.get("NO_COLOR") is not None:
        return True
    return not sys.stdout.isatty()


# Maps CLI type shorthand to template name
TYPE_TEMPLATE_MAP = {
    "bug": "bug_report",
    "feat": "feature_request",
    "ui": "ui_regression",
}


def _tool_version() -> str:
    """Return the installed distribution version."""
    try:
        return importlib.metadata.version("repo-issue")
    except importlib.metadata.PackageNotFoundError:
        return "unknown (package not installed)"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments with subparsers for each command."""
    parser = argparse.ArgumentParser(
        prog="issue",
        description="Local issue management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  init        Scaffold issues/ directory in the current repo
  list        List and filter issues (active by default)
  create      Create a new issue from template
  update      Update issue status (open/in_progress/resolved/cancelled)
  show        Display full issue content
  template    Print a template body skeleton (fill in, pass to create --body-file)
  search      Full-text search across all issues
  stats       Summary statistics (counts by type, status, priority)
  reconcile   Verify file/counter consistency

JSON output (--json):
  list        Array of issue objects
  list --labels  Object with label names as keys, counts as values
  create      Object with id, type, status, priority, file
  update      Object with id, status, file
  show        Object with frontmatter fields plus body
  search      Array of matching issue objects
  stats       Object with total, active, resolved, by_type, by_status, by_priority

Exit codes:
  0  success
  1  operation error (not found, no issues dir, consistency problems)
  2  usage error (invalid arguments)

Filters (for 'list' command):
  bug, feat, ui                 Type shorthand
  open, in_progress, ...        Status shorthand
  type:FEAT                     Explicit type filter
  status:open                   Explicit status filter
  priority:p0                   Priority filter (p0/p1/p2/p3)
  label:rendering               Label filter (partial match)

Examples:
  issue init                          Scaffold issues/ in current repo
  issue list                          Active issues
  issue list bug open                 Open bugs only
  issue list --all --json             All issues as JSON
  issue list priority:p0              P0 issues only
  issue create bug "Fix crash" -p p0  Create P0 bug
  issue create bug "Crash" -d -       Description from stdin (no shell quoting)
  issue create bug "Crash" --description-file notes.md
  issue template bug > body.md        Print skeleton, fill it, then:
  issue create bug "Crash" --body-file body.md --json
  issue update BUG-001 resolved       Resolve issue
  issue search "null pointer"         Search all issues
  issue search "crash" --json         Search results as JSON
  issue stats                         Show counts
  issue stats --json                  Stats as JSON
  issue reconcile                     Check consistency
""",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_tool_version()}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- init ---
    subparsers.add_parser(
        "init",
        help="Scaffold issues/ directory in the current repo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- list ---
    list_parser = subparsers.add_parser(
        "list",
        help="List and filter issue tickets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument(
        "filters",
        nargs="*",
        help="Filter criteria (type, status, priority, label)",
    )
    list_parser.add_argument(
        "--labels",
        action="store_true",
        help="List all unique labels with counts",
    )
    list_parser.add_argument(
        "--resolved",
        action="store_true",
        help="Include resolved/cancelled issues",
    )
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Show all issues (active + resolved)",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON (machine-readable)",
    )

    # --- create ---
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new issue from template",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Content channels (mutually exclusive):
  -d TEXT / -d -           Short summary (- reads stdin); ticket body becomes
                           a single '## Summary' section
  --description-file PATH  Same as -d, loaded from a file (- reads stdin)
  --body-file PATH         Full markdown body replacing the template body
                           (- reads stdin); must not contain frontmatter
  (none)                   Full template skeleton kept for later editing

Examples:
  issue create bug "Fix crash"
  issue create feat "Dark mode" -d "Add a dark color scheme" -p p1
  issue create bug "Crash on save" --description-file notes.md
  issue template bug > body.md   # fill it in, then:
  issue create bug "Crash on save" --body-file body.md --json
""",
    )
    create_parser.add_argument(
        "type",
        choices=["bug", "feat", "ui"],
        help="Issue type (bug, feat, or ui)",
    )
    create_parser.add_argument(
        "title",
        help="Issue title",
    )
    content_group = create_parser.add_mutually_exclusive_group()
    content_group.add_argument(
        "--description",
        "-d",
        default=None,
        help="Short summary text; use '-' to read from stdin",
    )
    content_group.add_argument(
        "--description-file",
        default=None,
        metavar="PATH",
        help="Read the summary from a file; use '-' to read from stdin",
    )
    content_group.add_argument(
        "--body-file",
        default=None,
        metavar="PATH",
        help="Read the full issue body from a file; use '-' to read from stdin",
    )
    create_parser.add_argument(
        "--author",
        "-a",
        default="agent",
        help="Author name (default: agent)",
    )
    create_parser.add_argument(
        "--priority",
        "-p",
        default=None,
        choices=["p0", "p1", "p2", "p3"],
        help="Priority (p0=critical, p1=high, p2=medium, p3=low)",
    )
    create_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output creation result as JSON",
    )

    # --- update ---
    update_parser = subparsers.add_parser(
        "update",
        help="Update issue status and manage lifecycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    update_parser.add_argument(
        "issue_id",
        help="Issue ID (e.g., BUG-001, FEAT-002)",
    )
    update_parser.add_argument(
        "status",
        choices=["open", "in_progress", "resolved", "cancelled"],
        help="New status for the issue",
    )
    update_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output update result as JSON",
    )

    # --- show ---
    show_parser = subparsers.add_parser(
        "show",
        help="Display full issue details",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show_parser.add_argument(
        "issue_id",
        help="Issue ID to display (e.g., BUG-001)",
    )
    show_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output frontmatter and body as JSON",
    )

    # --- template ---
    template_parser = subparsers.add_parser(
        "template",
        help="Print a template body skeleton for filling in",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Prints the body sections of the repo's issue template (frontmatter is
managed by the tool and omitted). Typical agent workflow:

  issue template bug > body.md   # fill in the sections
  issue create bug "Crash on save" --body-file body.md
""",
    )
    template_parser.add_argument(
        "type",
        choices=["bug", "feat", "ui"],
        help="Issue type (bug, feat, or ui)",
    )

    # --- search ---
    search_parser = subparsers.add_parser(
        "search",
        help="Full-text search across all issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    search_parser.add_argument(
        "query",
        help="Search query (case-insensitive substring match)",
    )
    search_parser.add_argument(
        "--resolved",
        action="store_true",
        help="Also search resolved issues",
    )
    search_parser.add_argument(
        "--all",
        action="store_true",
        help="Search all issues (active + resolved)",
    )
    search_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output matching issues as JSON array",
    )

    # --- stats ---
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show summary statistics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    stats_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output statistics as JSON",
    )

    # --- reconcile ---
    subparsers.add_parser(
        "reconcile",
        help="Check consistency between files and counters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    return parser.parse_args(args)


# ---------------------------------------------------------------------------
# Issue loading
# ---------------------------------------------------------------------------


def _load_issues_from_dir(directory: Path) -> list[dict[str, Any]]:
    """Load issues from a single directory.

    Internal keys (stripped from JSON output):
        _file: source file path
        _content: full file text (used by full-text search)
    """
    if not directory.exists():
        return []

    issues: list[dict[str, Any]] = []
    for file_path in directory.glob("*.md"):
        try:
            content = file_path.read_text()
            data = parse_yaml_frontmatter(content)
            if data and "id" in data:
                if "labels" not in data or not isinstance(data["labels"], list):
                    data["labels"] = []
                if "blocked_by" not in data or not isinstance(data["blocked_by"], list):
                    data["blocked_by"] = []
                data["_file"] = str(file_path)
                data["_content"] = content
                issues.append(data)
        except (OSError, UnicodeDecodeError):
            continue
    return issues


def load_issues(
    issues_dir: Path, *, include_resolved: bool = False
) -> list[dict[str, Any]]:
    """Load issues from active (and optionally resolved) directories."""
    issues = _load_issues_from_dir(issues_dir / "active")
    if include_resolved:
        issues.extend(_load_issues_from_dir(issues_dir / "resolved"))
    return issues


# ---------------------------------------------------------------------------
# Filtering and sorting
# ---------------------------------------------------------------------------

_STATUS_ORDER = {"open": 0, "in_progress": 1, "resolved": 2, "cancelled": 3}
_PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}


def _extract_issue_number(issue_id: str) -> int:
    """Extract numeric portion from issue ID like 'FEAT-048' -> 48."""
    match = re.search(r"(\d+)$", issue_id)
    return int(match.group(1)) if match else 0


def _issue_sort_key(issue: dict[str, Any]) -> tuple[int, int, int]:
    """Sort key: priority first, then status, then numeric ID."""
    priority = issue.get("priority", "p2")
    status = issue.get("status", "")
    issue_id = issue.get("id", "")
    return (
        _PRIORITY_ORDER.get(priority, 99),
        _STATUS_ORDER.get(status, 99),
        _extract_issue_number(issue_id),
    )


def issue_matches_filters(issue: dict[str, Any], filters: list[str]) -> bool:
    """Check if an issue matches all provided filters (AND logic)."""
    for filter_str in filters:
        filter_lower = filter_str.lower()

        # Explicit type: prefix
        if filter_str.startswith("type:"):
            issue_type = filter_str.split(":", 1)[1].upper()
            if issue.get("type", "").upper() != issue_type:
                return False

        # Explicit status: prefix
        elif filter_str.startswith("status:"):
            status = filter_str.split(":", 1)[1].lower()
            if issue.get("status", "").lower() != status:
                return False

        # Explicit priority: prefix
        elif filter_str.startswith("priority:"):
            priority = filter_str.split(":", 1)[1].lower()
            if issue.get("priority", "").lower() != priority:
                return False

        # Label filter
        elif filter_str.startswith("label:"):
            label_filter = filter_str[6:].lower()
            labels = issue.get("labels", [])
            if not any(label_filter in label.lower() for label in labels):
                return False

        # Type shorthand
        elif filter_lower in ("bug", "feat", "ui"):
            if issue.get("type", "").lower() != filter_lower:
                return False

        # Status shorthand
        elif filter_lower in ("open", "in_progress", "resolved", "cancelled"):
            if issue.get("status", "").lower() != filter_lower:
                return False

    return True


def filter_issues(
    issues: list[dict[str, Any]], filters: list[str]
) -> list[dict[str, Any]]:
    """Apply filters to issues. Multiple filters combine with AND logic."""
    if not filters:
        return issues
    return [i for i in issues if issue_matches_filters(i, filters)]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def get_colors(no_color: bool = False) -> dict[str, str]:
    """Get ANSI color codes based on no_color flag."""
    if no_color:
        return dict.fromkeys(
            ["reset", "bold", "bug", "feat", "ui", "dim", "p0", "p1", "p2", "p3"], ""
        )
    return {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "bug": "\033[1;31m",
        "feat": "\033[1;32m",
        "ui": "\033[1;33m",
        "dim": "\033[2m",
        "p0": "\033[1;31m",  # bold red
        "p1": "\033[1;33m",  # bold yellow
        "p2": "\033[0m",  # normal
        "p3": "\033[2m",  # dim
    }


def group_issues_by_type(
    issues: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group issues by their type field."""
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in issues:
        issue_type = issue.get("type", "UNKNOWN")
        by_type[issue_type].append(issue)
    return by_type


def format_output(
    issues: list[dict[str, Any]],
    no_color: bool = False,
) -> str:
    """Format issues for human-readable display."""
    if not issues:
        return "No issues match the criteria."

    colors = get_colors(no_color)
    by_type = group_issues_by_type(issues)

    for issue_type in by_type:
        by_type[issue_type].sort(key=_issue_sort_key)

    lines = []
    for issue_type in ["BUG", "FEAT", "UI"]:
        if issue_type not in by_type:
            continue

        type_issues = by_type[issue_type]
        header_color = colors.get(issue_type.lower(), colors["bold"])
        lines.append(
            f"{header_color}{issue_type}{colors['reset']} ({len(type_issues)} issues)"
        )

        for issue in type_issues:
            status = issue.get("status", "")
            issue_id = issue.get("id", "")
            title = issue.get("title", "")
            priority = issue.get("priority", "")
            blocked_by = issue.get("blocked_by", [])

            priority_tag = ""
            if priority:
                p_color = colors.get(priority, "")
                priority_tag = f" {p_color}[{priority}]{colors['reset']}"

            blocker_tag = ""
            if blocked_by:
                blocker_tag = f" {colors['dim']}blocked_by:{','.join(blocked_by)}{colors['reset']}"

            lines.append(
                f"  {colors['dim']}{status}{colors['reset']}  #{issue_id}  "
                f"{title}{priority_tag}{blocker_tag}"
            )

        lines.append("")

    return "\n".join(lines)


def format_issues_json(issues: list[dict[str, Any]]) -> str:
    """Format issues as JSON for machine consumption."""
    clean = []
    for issue in issues:
        entry = {k: v for k, v in issue.items() if not k.startswith("_")}
        clean.append(entry)
    return json.dumps(clean, indent=2, ensure_ascii=False)


def get_all_labels(issues: list[dict[str, Any]]) -> dict[str, int]:
    """Get all unique labels with counts."""
    label_counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        for label in issue.get("labels", []):
            if isinstance(label, str):
                label_counts[label] += 1
    return dict(sorted(label_counts.items()))


def format_labels(label_counts: dict[str, int]) -> str:
    """Format label listing output."""
    if not label_counts:
        return "No labels found."
    lines = ["Labels:"]
    for label, count in label_counts.items():
        lines.append(f"  {label}: {count}")
    return "\n".join(lines)


def find_issue_file(issues_dir: Path, issue_id: str) -> Path | None:
    """Find issue file in active or resolved directories."""
    active_path = issues_dir / "active" / f"{issue_id}.md"
    resolved_path = issues_dir / "resolved" / f"{issue_id}.md"

    if active_path.exists():
        return active_path
    if resolved_path.exists():
        return resolved_path
    return None


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle init command — scaffold issues/ in the current directory."""
    try:
        created = init_issues_dir(Path.cwd())
        print(f"Initialized issues directory: {created}")
        return 0
    except IssuesInitError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle list command."""
    include_resolved = getattr(args, "resolved", False) or getattr(args, "all", False)
    issues = load_issues(issues_dir, include_resolved=include_resolved)

    if getattr(args, "labels", False):
        label_counts = get_all_labels(issues)
        if getattr(args, "json_output", False):
            print(json.dumps(label_counts, indent=2))
        else:
            print(format_labels(label_counts))
        return 0

    if args.filters:
        issues = filter_issues(issues, args.filters)

    if getattr(args, "json_output", False):
        print(format_issues_json(issues))
    else:
        print(format_output(issues, no_color=should_disable_color()))
    return 0


def cmd_create(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle create command."""
    template_name = TYPE_TEMPLATE_MAP[args.type]

    try:
        description = None
        body = None
        if args.description is not None:
            description = _read_text_arg(args.description)
        elif args.description_file is not None:
            description = _read_file_arg(args.description_file)
        elif args.body_file is not None:
            body = _read_file_arg(args.body_file)

        issue_path = create_issue(
            template_name=template_name,
            title=args.title,
            description=description,
            body=body,
            author=args.author,
            priority=args.priority,
            issues_dir=issues_dir,
        )

        issue_id = issue_path.stem
        if args.json_output:
            print(
                json.dumps(
                    {
                        "id": issue_id,
                        "type": args.type,
                        "status": "open",
                        "priority": args.priority,
                        "file": str(issue_path),
                    },
                    indent=2,
                )
            )
        else:
            print(f"Created: {issue_id}")
            print(f"Type: {args.type}")
            print(f"File: {issue_path}")
            if args.priority:
                print(f"Priority: {args.priority}")
        return 0
    except (IssueCreationError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _read_text_arg(value: str) -> str:
    """Resolve a text argument; '-' means read from stdin."""
    if value == "-":
        return sys.stdin.read()
    return value


def _read_file_arg(path: str) -> str:
    """Read text from a file path; '-' means read from stdin."""
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text()


def cmd_template(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle template command - print the body skeleton for filling in."""
    template_name = TYPE_TEMPLATE_MAP[args.type]
    template_path = issues_dir / "templates" / f"{template_name}.md"

    if not template_path.exists():
        print(
            f"Error: Template not found: {template_path}\n"
            f"  Hint: run 'issue init' to restore bundled templates",
            file=sys.stderr,
        )
        return 1

    content = template_path.read_text()
    _, body = split_frontmatter_raw(content)
    print(body.strip())
    return 0


def cmd_update(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle update command."""
    try:
        target_path = update_issue_status(issues_dir, args.issue_id, args.status)
        if getattr(args, "json_output", False):
            print(
                json.dumps(
                    {
                        "id": args.issue_id,
                        "status": args.status,
                        "file": str(target_path),
                    },
                    indent=2,
                )
            )
        else:
            print(f"Updated: {args.issue_id} -> {args.status}")
            print(f"File: {target_path}")
        return 0
    except IssueUpdateError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_show(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle show command."""
    issue_id = args.issue_id.upper()
    issue_file = find_issue_file(issues_dir, issue_id)

    if not issue_file:
        # Try case-insensitive match
        issue_file = find_issue_file(issues_dir, args.issue_id)

    if not issue_file:
        print(
            f"Error: Issue not found: {args.issue_id}\n"
            f"  Hint: use 'issue list' to see active issues\n"
            f"  Hint: use 'issue list --all' to include resolved",
            file=sys.stderr,
        )
        return 1

    try:
        content = issue_file.read_text()

        if getattr(args, "json_output", False):
            data = parse_yaml_frontmatter(content) or {}
            _, body = split_frontmatter_raw(content)
            data["body"] = body
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(content)
        return 0
    except Exception as e:
        print(f"Error reading issue: {e}", file=sys.stderr)
        return 1


def cmd_search(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle search command — full-text search across issues."""
    include_resolved = getattr(args, "resolved", False) or getattr(args, "all", False)
    query_lower = args.query.lower()

    issues = load_issues(issues_dir, include_resolved=include_resolved)
    results = [i for i in issues if query_lower in i["_content"].lower()]
    results.sort(key=_issue_sort_key)

    results.sort(key=_issue_sort_key)

    # JSON output
    if getattr(args, "json_output", False):
        clean = [
            {k: v for k, v in issue.items() if not k.startswith("_")}
            for issue in results
        ]
        print(json.dumps(clean, indent=2, ensure_ascii=False))
        return 0

    # Human-readable output
    if not results:
        print(f"No issues match query: '{args.query}'")
        if not include_resolved:
            print("  Hint: use --all to also search resolved issues")
        return 0

    print(f"Found {len(results)} issue(s) matching '{args.query}':\n")
    for issue in results:
        issue_id = issue.get("id", "")
        title = issue.get("title", "")
        status = issue.get("status", "")
        print(f"  {status:<12} #{issue_id}  {title}")

    return 0


def cmd_stats(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle stats command — summary statistics."""
    active = _load_issues_from_dir(issues_dir / "active")
    resolved = _load_issues_from_dir(issues_dir / "resolved")

    all_issues = active + resolved

    # Count by type
    type_counts: dict[str, int] = defaultdict(int)
    for issue in all_issues:
        type_counts[issue.get("type", "UNKNOWN")] += 1

    # Count by status
    status_counts: dict[str, int] = defaultdict(int)
    for issue in all_issues:
        status_counts[issue.get("status", "unknown")] += 1

    # Count by priority (active only)
    priority_counts: dict[str, int] = defaultdict(int)
    for issue in active:
        priority_counts[issue.get("priority", "unset")] += 1

    # JSON output
    if getattr(args, "json_output", False):
        data = {
            "total": len(all_issues),
            "active": len(active),
            "resolved": len(resolved),
            "by_type": dict(type_counts),
            "by_status": dict(status_counts),
            "by_priority": dict(priority_counts),
        }
        print(json.dumps(data, indent=2))
        return 0

    # Human-readable output
    print(
        f"Total: {len(all_issues)} issues ({len(active)} active, {len(resolved)} resolved)\n"
    )

    print("By type:")
    for t in ["BUG", "FEAT", "UI"]:
        if type_counts.get(t, 0) > 0:
            print(f"  {t}: {type_counts[t]}")

    print("\nBy status:")
    for s in ["open", "in_progress", "resolved", "cancelled"]:
        if status_counts.get(s, 0) > 0:
            print(f"  {s}: {status_counts[s]}")

    print("\nActive by priority:")
    for p in ["p0", "p1", "p2", "p3", "unset"]:
        if priority_counts.get(p, 0) > 0:
            print(f"  {p}: {priority_counts[p]}")

    # Show blocked issues
    blocked = [i for i in active if i.get("blocked_by")]
    if blocked:
        print(f"\nBlocked issues ({len(blocked)}):")
        for issue in blocked:
            blockers = ", ".join(issue["blocked_by"])
            print(f"  #{issue['id']}  blocked by: {blockers}")

    return 0


def cmd_reconcile(args: argparse.Namespace, issues_dir: Path) -> int:
    """Handle reconcile command — check file/counter consistency."""
    counters_path = issues_dir / "counters.json"
    active_dir = issues_dir / "active"
    resolved_dir = issues_dir / "resolved"

    problems: list[str] = []

    # Load counters
    if not counters_path.exists():
        problems.append("MISSING: counters.json not found")
        counters = {}
    else:
        try:
            counters = json.loads(counters_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            problems.append(f"CORRUPT: counters.json: {e}")
            counters = {}

    # Scan all files and find max IDs per prefix
    file_max: dict[str, int] = defaultdict(int)
    file_counts: dict[str, int] = defaultdict(int)
    orphans: list[str] = []

    for directory in [active_dir, resolved_dir]:
        if not directory.exists():
            continue
        for file_path in directory.glob("*.md"):
            match = re.match(r"^([A-Z]+)-(\d+)\.md$", file_path.name)
            if not match:
                orphans.append(str(file_path))
                continue

            prefix = match.group(1)
            num = int(match.group(2))
            file_max[prefix] = max(file_max[prefix], num)
            file_counts[prefix] += 1

            # Verify frontmatter has matching id
            try:
                content = file_path.read_text()
                data = parse_yaml_frontmatter(content)
                if data:
                    fm_id = data.get("id", "")
                    expected_id = f"{prefix}-{num:03d}"
                    if fm_id != expected_id:
                        problems.append(
                            f"MISMATCH: {file_path.name} frontmatter id='{fm_id}' "
                            f"expected='{expected_id}'"
                        )
            except (OSError, UnicodeDecodeError):
                problems.append(f"UNREADABLE: {file_path}")

    # Note: counter behind file max is NOT a problem. Tickets imported from
    # other repos keep their original (possibly higher) IDs, and ID allocation
    # skips numbers already taken by files (see create_issue._next_free_number).

    if orphans:
        for orphan in orphans:
            problems.append(f"ORPHAN: non-standard filename: {orphan}")

    # Check for issues in active that are resolved/cancelled
    active_issues = _load_issues_from_dir(active_dir)
    for issue in active_issues:
        status = issue.get("status", "")
        if status in ("resolved", "cancelled"):
            problems.append(
                f"MISPLACED: {issue['id']} has status='{status}' but is in active/"
            )

    # Report
    if not problems:
        print("OK: All checks passed.")
        print(
            f"  Prefixes: {', '.join(f'{k}={v}' for k, v in sorted(counters.items()))}"
        )
        print(
            f"  Files: {sum(file_counts.values())} total ({', '.join(f'{k}:{v}' for k, v in sorted(file_counts.items()))})"
        )
        return 0

    print(f"Found {len(problems)} problem(s):\n")
    for problem in problems:
        print(f"  {problem}")
    print("\nHint: fix manually or re-run after corrections.")
    return 1


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_command(args: argparse.Namespace, issues_dir: Path) -> int:
    """Dispatch to appropriate command handler."""
    commands = {
        "init": cmd_init,
        "list": cmd_list,
        "create": cmd_create,
        "update": cmd_update,
        "show": cmd_show,
        "template": cmd_template,
        "search": cmd_search,
        "stats": cmd_stats,
        "reconcile": cmd_reconcile,
    }

    # argparse subparsers guarantee args.command is a known command
    return commands[args.command](args, issues_dir)


def main() -> int:
    """Main entry point."""
    args = parse_args()

    if args.command is None:
        print(
            "Error: No command specified.\n"
            "  Usage: issue <command> [args...]\n"
            "  Commands: init, list, create, update, show, template, search, "
            "stats, reconcile\n"
            "  Run 'issue --help' for full usage.",
            file=sys.stderr,
        )
        return 1

    # init scaffolds a new data dir; all other commands require an existing one.
    if args.command == "init":
        return cmd_init(args, Path.cwd())

    try:
        issues_dir = find_issues_dir()
    except IssuesDirNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return dispatch_command(args, issues_dir)


if __name__ == "__main__":
    sys.exit(main())
