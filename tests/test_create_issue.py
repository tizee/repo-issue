"""Tests for issue creation functionality."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from issue_tracker.create_issue import (
    IssueCreationError,
    _init_counters,
    create_issue,
    get_next_id,
)
from issue_tracker.yaml_utils import parse_yaml_frontmatter


@pytest.fixture
def temp_issues_dir():
    """Create a temporary directory structure for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    issues_dir = temp_dir / "issues"
    issues_dir.mkdir()
    (issues_dir / "active").mkdir()
    (issues_dir / "resolved").mkdir()
    (issues_dir / "templates").mkdir()

    # Create a minimal bug report template
    bug_template = issues_dir / "templates" / "bug_report.md"
    bug_template.write_text("""---
id: {{ID}}
title: "{{TITLE}}"
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: BUG
priority: p2
---

## Summary
<!-- Brief description of the bug -->

## Steps to Reproduce
1. <!-- Step 1 -->
""")

    # Create feature template
    feat_template = issues_dir / "templates" / "feature_request.md"
    feat_template.write_text("""---
id: {{ID}}
title: {{TITLE}}
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: FEAT
---

## Summary
""")

    # Create UI template
    ui_template = issues_dir / "templates" / "ui_regression.md"
    ui_template.write_text("""---
id: {{ID}}
title: {{TITLE}}
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: UI
---

## Summary
""")

    yield issues_dir

    # Cleanup
    shutil.rmtree(temp_dir)


class TestInitCounters:
    """Tests for counter initialization."""

    def test_init_creates_file_with_defaults(self, temp_issues_dir):
        """Test that _init_counters creates file with correct defaults."""
        counters_path = temp_issues_dir / "counters.json"

        _init_counters(counters_path)

        assert counters_path.exists()
        data = json.loads(counters_path.read_text())
        assert data == {"BUG": 0, "FEAT": 0, "UI": 0}


class TestGetNextId:
    """Tests for ID generation."""

    def test_first_id(self, temp_issues_dir):
        """Test getting first ID for a prefix."""
        with patch("issue_tracker.create_issue._init_counters") as mock_init:
            mock_init.return_value = None
            issue_id = get_next_id(temp_issues_dir, "BUG")

        assert issue_id == "BUG-001"

    def test_sequential_ids(self, temp_issues_dir):
        """Test that IDs are sequential."""
        counters_path = temp_issues_dir / "counters.json"
        counters_path.write_text(json.dumps({"BUG": 3, "FEAT": 0, "UI": 0}))

        issue_id = get_next_id(temp_issues_dir, "BUG")

        assert issue_id == "BUG-004"

    def test_independent_prefixes(self, temp_issues_dir):
        """Test that different prefixes have independent counters."""
        counters_path = temp_issues_dir / "counters.json"
        counters_path.write_text(json.dumps({"BUG": 5, "FEAT": 2, "UI": 0}))

        bug_id = get_next_id(temp_issues_dir, "BUG")
        feat_id = get_next_id(temp_issues_dir, "FEAT")

        assert bug_id == "BUG-006"
        assert feat_id == "FEAT-003"

    def test_fallback_to_directory_scan(self, temp_issues_dir):
        """Test fallback when counters.json is corrupt."""
        # Create existing issue files
        (temp_issues_dir / "active" / "UI-001.md").write_text("test")
        (temp_issues_dir / "active" / "UI-003.md").write_text("test")
        (temp_issues_dir / "resolved" / "UI-002.md").write_text("test")

        # Create corrupt counters file
        counters_path = temp_issues_dir / "counters.json"
        counters_path.write_text("invalid json")

        with patch("builtins.print"):
            issue_id = get_next_id(temp_issues_dir, "UI")

        assert issue_id == "UI-004"


class TestCreateIssue:
    """Tests for issue creation."""

    def test_create_bug_report(self, temp_issues_dir):
        """Test creating a bug report."""
        issue_path = create_issue(
            template_name="bug_report",
            title="Test Bug",
            issues_dir=temp_issues_dir,
            description="This is a test bug",
            author="test_user",
        )

        assert issue_path.exists()
        content = issue_path.read_text()
        assert "id: BUG-001" in content
        assert "title: Test Bug" in content
        assert "status: open" in content
        assert "author: test_user" in content
        assert "## Summary" in content
        assert "This is a test bug" in content

    def test_create_feature_request(self, temp_issues_dir):
        """Test creating a feature request."""
        issue_path = create_issue(
            template_name="feature_request",
            title="New Feature",
            issues_dir=temp_issues_dir,
            author="agent",
        )

        assert issue_path.exists()
        content = issue_path.read_text()
        assert "id: FEAT-001" in content
        assert "title: New Feature" in content
        assert "type: FEAT" in content

    def test_create_without_description(self, temp_issues_dir):
        """Test creating an issue without description."""
        issue_path = create_issue(
            template_name="bug_report",
            title="Bug without description",
            issues_dir=temp_issues_dir,
        )

        assert issue_path.exists()
        content = issue_path.read_text()
        assert "title: Bug without description" in content

    def test_bare_create_keeps_full_template(self, temp_issues_dir):
        """Without description or body, the template skeleton is preserved
        as a fill-in prompt for whoever edits the ticket later."""
        issue_path = create_issue(
            template_name="bug_report",
            title="Skeleton bug",
            issues_dir=temp_issues_dir,
        )

        content = issue_path.read_text()
        assert "## Steps to Reproduce" in content

    def test_description_produces_summary_only_body(self, temp_issues_dir):
        """A described ticket carries no unfilled template skeleton.

        Regression: tickets used to keep dozens of placeholder comment lines
        (<!-- Step 1 --> etc.) that nobody ever filled in — pure byte waste.
        """
        issue_path = create_issue(
            template_name="bug_report",
            title="Described bug",
            issues_dir=temp_issues_dir,
            description="Crash when saving.\n\nStack trace attached.",
        )

        content = issue_path.read_text()
        assert "## Summary" in content
        assert "Crash when saving." in content
        assert "<!--" not in content
        assert "## Steps to Reproduce" not in content

    def test_priority_written_into_frontmatter(self, temp_issues_dir):
        """Priority given at creation lands in frontmatter."""
        issue_path = create_issue(
            template_name="bug_report",
            title="Urgent bug",
            issues_dir=temp_issues_dir,
            priority="p0",
        )

        data = parse_yaml_frontmatter(issue_path.read_text())
        assert data["priority"] == "p0"

    def test_body_replaces_template_body(self, temp_issues_dir):
        """A caller-supplied body replaces the template body entirely;
        frontmatter (id, dates, type) stays tool-owned."""
        issue_path = create_issue(
            template_name="bug_report",
            title="Full body bug",
            issues_dir=temp_issues_dir,
            body="## Summary\nCustom body.\n\n## Analysis\nDeep dive.\n",
        )

        content = issue_path.read_text()
        data = parse_yaml_frontmatter(content)
        assert data["id"] == "BUG-001"
        assert data["type"] == "BUG"
        assert "## Analysis" in content
        assert "<!--" not in content

    def test_body_with_frontmatter_rejected(self, temp_issues_dir):
        """Bodies must not smuggle in their own frontmatter — fail fast."""
        with pytest.raises(IssueCreationError, match="frontmatter"):
            create_issue(
                template_name="bug_report",
                title="Sneaky",
                issues_dir=temp_issues_dir,
                body="---\nid: FAKE-999\n---\nbody",
            )

    def test_description_and_body_are_exclusive(self, temp_issues_dir):
        """description and body cannot both be given — ambiguous intent."""
        with pytest.raises(IssueCreationError):
            create_issue(
                template_name="bug_report",
                title="Ambiguous",
                issues_dir=temp_issues_dir,
                description="summary",
                body="## Summary\nbody",
            )

    def test_title_with_quotes_round_trips(self, temp_issues_dir):
        """Regression: quoted titles used to gain escape backslashes."""
        title = 'Fix "quoted" crash'
        issue_path = create_issue(
            template_name="bug_report",
            title=title,
            issues_dir=temp_issues_dir,
            priority="p1",
        )

        data = parse_yaml_frontmatter(issue_path.read_text())
        assert data["title"] == title

    def test_title_with_newline_rejected(self, temp_issues_dir):
        """Multi-line titles would corrupt frontmatter — fail fast."""
        with pytest.raises(IssueCreationError):
            create_issue(
                template_name="bug_report",
                title="line1\nline2",
                issues_dir=temp_issues_dir,
            )
