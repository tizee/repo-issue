"""Scaffold a new issues/ data directory in a repository.

Copies the bundled default templates and creates the directory layout:

    issues/
    |-- templates/      issue templates (editable per repo)
    |-- active/         open / in-progress issues
    |-- resolved/       resolved / cancelled issues
    `-- counters.json   per-prefix ID counters
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .discovery import ISSUES_DIR_NAME

_BUNDLED_TEMPLATES = Path(__file__).parent / "templates"

DEFAULT_COUNTERS = {"BUG": 0, "FEAT": 0, "SAFE": 0, "UI": 0, "DOCS": 0}


class IssuesInitError(Exception):
    """Error scaffolding the issues directory."""


def init_issues_dir(root: Path) -> Path:
    """Create issues/ structure under root. Idempotent for missing pieces.

    Raises:
        IssuesInitError: if an issues/ path exists but is not a directory.
    """
    issues_dir = root / ISSUES_DIR_NAME

    if issues_dir.exists() and not issues_dir.is_dir():
        raise IssuesInitError(f"{issues_dir} exists but is not a directory")

    (issues_dir / "active").mkdir(parents=True, exist_ok=True)
    (issues_dir / "resolved").mkdir(parents=True, exist_ok=True)

    templates_dir = issues_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    for template in _BUNDLED_TEMPLATES.glob("*.md"):
        target = templates_dir / template.name
        if not target.exists():
            shutil.copy(template, target)

    counters_path = issues_dir / "counters.json"
    if not counters_path.exists():
        counters_path.write_text(json.dumps(DEFAULT_COUNTERS, indent=2))

    return issues_dir
