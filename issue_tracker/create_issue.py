"""Create a new issue from template.

Templates:
    bug_report          - General bug report
    feature_request     - Feature request
    ui_regression       - Visual/UI rendering issue
    multi_agent_safety  - Multi-agent safety concern
"""

from __future__ import annotations

import fcntl
import json
import re
import sys
from datetime import datetime
from pathlib import Path

TEMPLATE_PREFIXES = {
    "bug_report": "BUG",
    "feature_request": "FEAT",
    "ui_regression": "UI",
    "multi_agent_safety": "SAFE",
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
    defaults = {"BUG": 0, "FEAT": 0, "SAFE": 0, "UI": 0, "DOCS": 0}
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
    author: str = "agent",
) -> Path:
    """Create a new issue from template.

    Args:
        template_name: Template to use (bug_report, feature_request, etc.)
        title: Issue title
        issues_dir: Issues data directory (see discovery.find_issues_dir)
        description: Optional description/summary
        author: Author name (default: agent)

    Returns:
        Path to created issue file

    Raises:
        IssueCreationError: If template is unknown or template file not found
    """
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
    escaped_title = title.replace('"', '\\"')
    content = template_content.replace("{{ID}}", issue_id)
    content = content.replace("{{TITLE}}", escaped_title)
    content = content.replace("{{DATE}}", datetime.now().strftime("%Y-%m-%d"))
    content = content.replace("{{AUTHOR}}", author)
    content = content.replace("{{STATUS}}", "open")

    # Add user description if provided (insert after Summary heading)
    if description:
        summary_marker = "## Summary\n"
        if summary_marker in content:
            # Find position after Summary heading
            pos = content.find(summary_marker) + len(summary_marker)
            # Check if there's a comment placeholder
            if content[pos:].startswith("<!--"):
                end_comment = content.find("-->", pos)
                if end_comment != -1:
                    # Replace the placeholder comment with description
                    content = content[:pos] + description + content[end_comment + 3 :]
            else:
                # Insert description after Summary heading
                content = content[:pos] + description + "\n\n" + content[pos:]

    # Write issue file
    active_dir.mkdir(parents=True, exist_ok=True)
    issue_path = active_dir / f"{issue_id}.md"
    issue_path.write_text(content)

    return issue_path
