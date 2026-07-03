"""Create a new issue from template.

Templates:
    bug_report          - General bug report
    feature_request     - Feature request
    ui_regression       - Visual/UI rendering issue
"""

from __future__ import annotations

import fcntl
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from .yaml_utils import set_frontmatter_field, split_frontmatter_raw

TEMPLATE_PREFIXES = {
    "bug_report": "BUG",
    "feature_request": "FEAT",
    "ui_regression": "UI",
}


def _id_taken(issues_dir: Path, prefix: str, num: int) -> bool:
    """Check whether an issue file with this ID already exists."""
    filename = f"{prefix}-{num:03d}.md"
    return (issues_dir / "active" / filename).exists() or (
        issues_dir / "resolved" / filename
    ).exists()


def _next_free_number(issues_dir: Path, prefix: str, start: int) -> int:
    """Return the first number >= start whose ID is not taken by a file.

    Tickets moved in from other repos keep their original IDs, so the
    counter may lag behind existing files. Skipping taken numbers keeps
    allocation collision-free without renumbering imported tickets.
    """
    num = start
    while _id_taken(issues_dir, prefix, num):
        num += 1
    return num


def get_next_id(issues_dir: Path, prefix: str) -> str:
    """Get the next available issue ID using atomic counter file.

    Uses counters.json with file locking to prevent race conditions.
    Skips numbers already taken by existing issue files (e.g. tickets
    imported from another repo with their original IDs preserved).
    Falls back to directory scan if counters.json is missing or corrupt.
    """
    counters_path = issues_dir / "counters.json"

    # Ensure counters file exists with defaults
    if not counters_path.exists():
        _init_counters(counters_path)

    try:
        with counters_path.open("r+") as f:
            # Acquire exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                counters = json.load(f)
                current = counters.get(prefix, 0)
                next_num = _next_free_number(issues_dir, prefix, current + 1)
                counters[prefix] = next_num

                # Write back
                f.seek(0)
                json.dump(counters, f, indent=2)
                f.truncate()

                return f"{prefix}-{next_num:03d}"
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(
            f"Warning: Counter file error ({e}), falling back to directory scan",
            file=sys.stderr,
        )
        return _get_next_id_fallback(issues_dir, prefix)


def _init_counters(counters_path: Path) -> None:
    """Initialize counters.json with default values if it doesn't exist."""
    defaults = dict.fromkeys(sorted(TEMPLATE_PREFIXES.values()), 0)
    counters_path.write_text(json.dumps(defaults, indent=2))


def _get_next_id_fallback(issues_dir: Path, prefix: str) -> str:
    """Fallback: scan directories to find max ID."""
    active_dir = issues_dir / "active"
    resolved_dir = issues_dir / "resolved"

    max_num = 0
    pattern = re.compile(rf"^{prefix}-(\d+)\.md$")

    for dir_path in [active_dir, resolved_dir]:
        if dir_path.exists():
            for file in dir_path.glob(f"{prefix}-*.md"):
                match = pattern.match(file.name)
                if match:
                    num = int(match.group(1))
                    max_num = max(max_num, num)

    return f"{prefix}-{max_num + 1:03d}"


class IssueCreationError(Exception):
    """Error creating an issue."""


def create_issue(
    template_name: str,
    title: str,
    issues_dir: Path,
    description: str | None = None,
    body: str | None = None,
    author: str = "agent",
    priority: str | None = None,
) -> Path:
    """Create a new issue from template.

    Content channels (mutually exclusive):
        description: Short summary. The ticket body becomes a single
            '## Summary' section - no unfilled template skeleton is kept.
        body: Full markdown body replacing the template body entirely.
            Frontmatter stays tool-owned; a body carrying its own
            frontmatter is rejected.
        neither: The full template skeleton is kept as a fill-in prompt.

    Args:
        template_name: Template to use (bug_report, feature_request, etc.)
        title: Issue title (single line)
        issues_dir: Issues data directory (see discovery.find_issues_dir)
        description: Optional description/summary
        body: Optional full body content
        author: Author name (default: agent)
        priority: Optional priority (p0-p3), written into frontmatter

    Returns:
        Path to created issue file

    Raises:
        IssueCreationError: On unknown template, missing template file,
            conflicting content channels, or malformed title/body.
    """
    if description is not None and body is not None:
        raise IssueCreationError(
            "description and body are mutually exclusive - provide one"
        )
    if "\n" in title:
        raise IssueCreationError("title must be a single line")
    if body is not None and body.lstrip().startswith("---"):
        raise IssueCreationError(
            "body must not contain frontmatter (--- block); "
            "id/status/dates are managed by the tool"
        )

    templates_dir = issues_dir / "templates"
    active_dir = issues_dir / "active"

    if template_name not in TEMPLATE_PREFIXES:
        available = ", ".join(TEMPLATE_PREFIXES.keys())
        raise IssueCreationError(
            f"Unknown template '{template_name}'. Available: {available}"
        )

    prefix = TEMPLATE_PREFIXES[template_name]
    issue_id = get_next_id(issues_dir, prefix)

    # Read template
    template_path = templates_dir / f"{template_name}.md"
    if not template_path.exists():
        raise IssueCreationError(f"Template not found: {template_path}")

    template_content = template_path.read_text()

    # Substitute variables in template
    content = template_content.replace("{{ID}}", issue_id)
    content = content.replace("{{TITLE}}", title)
    content = content.replace("{{DATE}}", datetime.now().strftime("%Y-%m-%d"))
    content = content.replace("{{AUTHOR}}", author)
    content = content.replace("{{STATUS}}", "open")

    # Normalize the title line: proper YAML quoting/escaping regardless of
    # how the template writes it (quoted or bare placeholder).
    try:
        content = set_frontmatter_field(content, "title", title)
        if priority:
            content = set_frontmatter_field(content, "priority", priority)
    except ValueError as e:
        raise IssueCreationError(f"Template {template_path} is malformed: {e}") from e

    frontmatter_block, _template_body = split_frontmatter_raw(content)
    if frontmatter_block is None:
        raise IssueCreationError(
            f"Template {template_path} has no YAML frontmatter block"
        )

    if body is not None:
        content = frontmatter_block + "\n" + body.strip() + "\n"
    elif description is not None:
        # Summary-only body: no dead placeholder skeleton. Agents that want
        # the full section structure use 'issue template' + body instead.
        content = frontmatter_block + "\n## Summary\n\n" + description.strip() + "\n"

    # Write issue file
    active_dir.mkdir(parents=True, exist_ok=True)
    issue_path = active_dir / f"{issue_id}.md"
    issue_path.write_text(content)

    return issue_path
