"""Tests for issue status update functionality."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from issue_tracker.update_status import IssueUpdateError, update_issue_status
from issue_tracker.yaml_utils import dump_yaml_frontmatter, split_frontmatter


@pytest.fixture
def temp_issues_dir():
    """Create a temporary directory structure for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    issues_dir = temp_dir / "issues"
    issues_dir.mkdir()
    (issues_dir / "active").mkdir()
    (issues_dir / "resolved").mkdir()

    yield issues_dir

    # Cleanup
    shutil.rmtree(temp_dir)


def _write_issue(path: Path, frontmatter: dict, body: str) -> None:
    """Write an issue file with frontmatter + body."""
    path.write_text(dump_yaml_frontmatter(frontmatter) + body)


class TestSplitFrontmatter:
    """Tests for frontmatter parsing."""

    def test_parse_valid_frontmatter(self):
        """Test parsing valid YAML frontmatter."""
        content = """---
id: BUG-001
title: Test Issue
status: open
created: 2026-02-03
---

## Summary
This is the body.
"""
        frontmatter, body = split_frontmatter(content)

        assert frontmatter is not None
        assert frontmatter["id"] == "BUG-001"
        assert frontmatter["title"] == "Test Issue"
        assert frontmatter["status"] == "open"
        assert "## Summary" in body
        assert "This is the body." in body

    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "## Summary\nNo frontmatter here."

        frontmatter, body = split_frontmatter(content)

        assert frontmatter is None
        assert body == content

    def test_parse_empty_frontmatter(self):
        """Test parsing empty frontmatter block."""
        content = """---
---

## Summary
Body here.
"""
        frontmatter, body = split_frontmatter(content)

        # Empty frontmatter returns empty dict
        if frontmatter is not None:
            assert frontmatter == {} or len(frontmatter) == 0
        assert "## Summary" in body


class TestDumpFrontmatter:
    """Tests for frontmatter serialization."""

    def test_dump_simple_frontmatter(self):
        """Test dumping simple frontmatter."""
        frontmatter = {"id": "BUG-001", "status": "open"}
        body = "## Summary\nTest"

        result = dump_yaml_frontmatter(frontmatter) + body

        assert result.startswith("---\n")
        assert "id: BUG-001" in result
        assert "status: open" in result
        assert result.endswith("## Summary\nTest")

    def test_dump_preserves_order(self):
        """Test that frontmatter keys preserve order."""
        frontmatter = {"id": "BUG-001", "title": "Test", "status": "open"}

        result = dump_yaml_frontmatter(frontmatter)

        # Check order: id should come before title before status
        id_pos = result.find("id:")
        title_pos = result.find("title:")
        status_pos = result.find("status:")

        assert id_pos < title_pos < status_pos


class TestUpdateIssueStatus:
    """Tests for status update functionality."""

    def create_test_issue(
        self, issues_dir: Path, issue_id: str, status: str, is_active: bool = True
    ) -> Path:
        """Helper to create a test issue file."""
        subdir = "active" if is_active else "resolved"
        issue_path = issues_dir / subdir / f"{issue_id}.md"

        frontmatter = {
            "id": issue_id,
            "title": f"Test {issue_id}",
            "created": "2026-02-03",
            "status": status,
            "author": "test",
        }

        if status in ("resolved", "cancelled"):
            frontmatter["resolved_date"] = "2026-02-03"

        _write_issue(issue_path, frontmatter, "## Summary\nTest content")
        return issue_path

    def test_update_to_resolved(self, temp_issues_dir):
        """Test updating an open issue to resolved."""
        self.create_test_issue(temp_issues_dir, "BUG-001", "open")

        target_path = update_issue_status(temp_issues_dir, "BUG-001", "resolved")

        # Check file moved to resolved
        assert target_path.parent.name == "resolved"

        # Check content updated
        content = target_path.read_text()
        frontmatter, _ = split_frontmatter(content)
        assert frontmatter["status"] == "resolved"
        assert "resolved_date" in frontmatter

    def test_update_to_in_progress(self, temp_issues_dir):
        """Test updating an open issue to in_progress."""
        self.create_test_issue(temp_issues_dir, "FEAT-002", "open")

        target_path = update_issue_status(temp_issues_dir, "FEAT-002", "in_progress")

        # Check still in active
        assert target_path.parent.name == "active"

        content = target_path.read_text()
        frontmatter, _ = split_frontmatter(content)
        assert frontmatter["status"] == "in_progress"
        assert "resolved_date" not in frontmatter

    def test_update_from_resolved_to_open(self, temp_issues_dir):
        """Test reopening a resolved issue."""
        self.create_test_issue(temp_issues_dir, "UI-003", "resolved", is_active=False)

        target_path = update_issue_status(temp_issues_dir, "UI-003", "open")

        # Check file moved back to active
        assert target_path.parent.name == "active"

        content = target_path.read_text()
        frontmatter, _ = split_frontmatter(content)
        assert frontmatter["status"] == "open"
        assert "resolved_date" not in frontmatter

    def test_update_cancelled(self, temp_issues_dir):
        """Test cancelling an issue."""
        self.create_test_issue(temp_issues_dir, "BUG-005", "in_progress")

        target_path = update_issue_status(temp_issues_dir, "BUG-005", "cancelled")

        assert target_path.parent.name == "resolved"

        content = target_path.read_text()
        frontmatter, _ = split_frontmatter(content)
        assert frontmatter["status"] == "cancelled"
        assert "resolved_date" in frontmatter

    def test_issue_not_found(self, temp_issues_dir):
        """Test updating non-existent issue raises error."""
        with pytest.raises(IssueUpdateError) as exc_info:
            update_issue_status(temp_issues_dir, "BUG-999", "resolved")

        assert "not found" in str(exc_info.value).lower()

    def test_update_preserves_body_content(self, temp_issues_dir):
        """Test that body content is preserved during status update."""
        issue_path = temp_issues_dir / "active" / "BUG-010.md"
        original_content = """---
id: BUG-010
title: Test
created: 2026-02-03
status: open
author: test
---

## Summary
Original summary with details.

## Steps to Reproduce
1. Step one
2. Step two

## Expected Behavior
It should work.
"""
        issue_path.write_text(original_content)

        target_path = update_issue_status(temp_issues_dir, "BUG-010", "resolved")

        content = target_path.read_text()
        assert "## Summary" in content
        assert "Original summary with details." in content
        assert "## Steps to Reproduce" in content
        assert "## Expected Behavior" in content
