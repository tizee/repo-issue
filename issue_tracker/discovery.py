"""Discovery of the repo-local issues/ data directory.

The CLI is installed globally but operates on per-repo ticket data. The
data directory is found by walking up from the current working directory
(like git finds .git/). Fail fast when none is found - no silent defaults.
"""

from __future__ import annotations

from pathlib import Path

ISSUES_DIR_NAME = "issues"


class IssuesDirNotFoundError(Exception):
    """No issues/ directory found walking up from the start path."""


def looks_like_issues_dir(path: Path) -> bool:
    """A directory qualifies as issues data if it has the expected markers."""
    if not path.is_dir():
        return False
    return (path / "counters.json").is_file() or (path / "active").is_dir()


def find_issues_dir(start: Path | None = None) -> Path:
    """Walk up from start (default: cwd) to find the issues/ directory.

    Also matches when start is the issues directory itself or inside it.

    Raises:
        IssuesDirNotFoundError: when no issues directory exists upward.
    """
    origin = (start or Path.cwd()).resolve()

    for candidate_root in [origin, *origin.parents]:
        # Allow running from inside the issues directory itself.
        if candidate_root.name == ISSUES_DIR_NAME and looks_like_issues_dir(
            candidate_root
        ):
            return candidate_root
        candidate = candidate_root / ISSUES_DIR_NAME
        if looks_like_issues_dir(candidate):
            return candidate

    raise IssuesDirNotFoundError(
        f"No '{ISSUES_DIR_NAME}/' directory found from {origin} upward.\n"
        f"  Hint: run 'issue init' at the repo root to scaffold one."
    )
