"""Update the status of an issue and manage its lifecycle.

Status values:
    open         - Issue is newly created (default)
    in_progress  - Issue is being worked on
    resolved     - Issue is completed
    cancelled    - Issue is no longer relevant
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .yaml_utils import parse_yaml_frontmatter, set_frontmatter_field

VALID_STATUSES = {"open", "in_progress", "resolved", "cancelled"}


class IssueUpdateError(Exception):
    """Error updating an issue status."""

    pass


def update_issue_status(
    issues_dir: Path,
    issue_id: str,
    new_status: str,
) -> Path:
    """Update an issue's status and move between directories if needed.

    Edits only the status/resolved_date frontmatter lines; every other
    field and the body pass through untouched.

    Raises:
        IssueUpdateError: If status is invalid, issue not found, or parse fails.
    """
    if new_status not in VALID_STATUSES:
        valid_list = ", ".join(sorted(VALID_STATUSES))
        raise IssueUpdateError(f"Invalid status '{new_status}'. Valid: {valid_list}")

    # Find the issue file
    active_dir = issues_dir / "active"
    resolved_dir = issues_dir / "resolved"

    active_path = active_dir / f"{issue_id}.md"
    resolved_path = resolved_dir / f"{issue_id}.md"

    if active_path.exists():
        source_path = active_path
    elif resolved_path.exists():
        source_path = resolved_path
    else:
        raise IssueUpdateError(
            f"Issue not found: {issue_id}\n"
            f"  Searched: {active_dir}/\n"
            f"  Searched: {resolved_dir}/\n"
            f"  Hint: use 'issue list' to see active issues"
        )

    content = source_path.read_text()
    frontmatter = parse_yaml_frontmatter(content)
    if frontmatter is None:
        raise IssueUpdateError(f"Failed to parse frontmatter in {source_path}")

    old_status = frontmatter.get("status", "unknown")

    new_content = set_frontmatter_field(content, "status", new_status)

    # Add resolved_date if transitioning to resolved/cancelled
    if new_status in ("resolved", "cancelled") and old_status not in (
        "resolved",
        "cancelled",
    ):
        new_content = set_frontmatter_field(
            new_content, "resolved_date", datetime.now().strftime("%Y-%m-%d")
        )

    # Remove resolved_date if transitioning back to open/in_progress
    if new_status in ("open", "in_progress"):
        new_content = set_frontmatter_field(new_content, "resolved_date", None)

    # Determine target path
    if new_status in ("resolved", "cancelled"):
        resolved_dir.mkdir(parents=True, exist_ok=True)
        target_path = resolved_path
    else:
        active_dir.mkdir(parents=True, exist_ok=True)
        target_path = active_path

    # If moving directories, remove from source
    if source_path != target_path:
        source_path.unlink()

    target_path.write_text(new_content)

    return target_path
