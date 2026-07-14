"""Tests for issue status update functionality."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from issue_tracker.update_status import (
    IssueUpdateError,
    add_issue_note,
    update_issue_status,
)
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

    def test_update_preserves_exotic_frontmatter(self, temp_issues_dir):
        """Fields the built-in parser cannot model survive a status update.

        update only needs to touch status/resolved_date; everything else in
        the frontmatter (custom fields, unusual values) must pass through
        byte-for-byte.
        """
        issue_path = temp_issues_dir / "active" / "BUG-020.md"
        issue_path.write_text("""---
id: BUG-020
title: "Complex: ticket [with] #special chars"
created: 2026-02-03
status: open
author: test
custom_metric: 42.5
owner_chain: alice -> bob
---

## Summary
Body.
""")

        target_path = update_issue_status(temp_issues_dir, "BUG-020", "in_progress")

        content = target_path.read_text()
        assert 'title: "Complex: ticket [with] #special chars"' in content
        assert "custom_metric: 42.5" in content
        assert "owner_chain: alice -> bob" in content
        assert "status: in_progress" in content

    def test_repeated_updates_do_not_corrupt_quoted_title(self, temp_issues_dir):
        """Regression: quoted titles used to gain backslashes on every update."""
        issue_path = temp_issues_dir / "active" / "BUG-021.md"
        issue_path.write_text("""---
id: BUG-021
title: "Title with \\"quotes\\" inside"
status: open
---

Body.
""")

        update_issue_status(temp_issues_dir, "BUG-021", "in_progress")
        update_issue_status(temp_issues_dir, "BUG-021", "open")
        path = update_issue_status(temp_issues_dir, "BUG-021", "in_progress")

        content = path.read_text()
        assert "\\\\" not in content, "backslashes must not accumulate"
        frontmatter, _ = split_frontmatter(content)
        assert frontmatter["title"] == 'Title with "quotes" inside'

    def test_note_appended_to_body_on_update(self, temp_issues_dir):
        """A note passed with the update is appended as a dated section.

        This is the core pain point: agents can record a resolution note in
        the same call that flips the status, instead of editing the file by
        hand first.
        """
        self.create_test_issue(temp_issues_dir, "BUG-030", "in_progress")

        target_path = update_issue_status(
            temp_issues_dir,
            "BUG-030",
            "resolved",
            note="Fixed by clamping the index in render().",
        )

        content = target_path.read_text()
        frontmatter, body = split_frontmatter(content)
        assert frontmatter["status"] == "resolved"
        # Original body survives
        assert "## Summary" in content
        assert "Test content" in content
        # Note section appended with a date heading and the note text
        assert "## Note" in body
        assert "Fixed by clamping the index in render()." in body

    def test_note_none_leaves_body_untouched(self, temp_issues_dir):
        """Without a note, the body is byte-for-byte unchanged apart from
        frontmatter edits (no stray Note heading)."""
        self.create_test_issue(temp_issues_dir, "BUG-031", "open")

        target_path = update_issue_status(temp_issues_dir, "BUG-031", "in_progress")

        content = target_path.read_text()
        assert "## Note" not in content

    def test_multiple_notes_accumulate(self, temp_issues_dir):
        """Notes from successive updates stack; earlier notes are preserved."""
        self.create_test_issue(temp_issues_dir, "BUG-032", "open")

        update_issue_status(
            temp_issues_dir, "BUG-032", "in_progress", note="Started investigating."
        )
        target_path = update_issue_status(
            temp_issues_dir, "BUG-032", "resolved", note="Root cause found and fixed."
        )

        content = target_path.read_text()
        assert "Started investigating." in content
        assert "Root cause found and fixed." in content
        assert content.count("## Note") == 2

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


class TestAddIssueNote:
    """Tests for appending a note without changing status."""

    def _make(self, issues_dir: Path, issue_id: str, status: str, active: bool = True):
        subdir = "active" if active else "resolved"
        path = issues_dir / subdir / f"{issue_id}.md"
        fm = {"id": issue_id, "title": f"Test {issue_id}", "status": status}
        _write_issue(path, fm, "## Summary\nOriginal body.")
        return path

    def test_note_appended_without_status_change(self, temp_issues_dir):
        """add_issue_note records a note but leaves status/location intact."""
        self._make(temp_issues_dir, "BUG-040", "in_progress")

        path = add_issue_note(temp_issues_dir, "BUG-040", "Progress: found the bug.")

        # Stays in active, status unchanged
        assert path.parent.name == "active"
        content = path.read_text()
        frontmatter, body = split_frontmatter(content)
        assert frontmatter["status"] == "in_progress"
        assert "## Note" in body
        assert "Progress: found the bug." in body
        assert "Original body." in body

    def test_note_on_resolved_issue_stays_resolved(self, temp_issues_dir):
        """Adding a note to a resolved ticket does not move it back to active."""
        self._make(temp_issues_dir, "BUG-041", "resolved", active=False)

        path = add_issue_note(temp_issues_dir, "BUG-041", "Follow-up observation.")

        assert path.parent.name == "resolved"
        assert "Follow-up observation." in path.read_text()

    def test_empty_note_rejected(self, temp_issues_dir):
        """An empty/whitespace note is an error, not a no-op write."""
        self._make(temp_issues_dir, "BUG-042", "open")

        with pytest.raises(IssueUpdateError):
            add_issue_note(temp_issues_dir, "BUG-042", "   ")

    def test_note_on_missing_issue_raises(self, temp_issues_dir):
        """Noting a non-existent issue raises with a helpful message."""
        with pytest.raises(IssueUpdateError) as exc_info:
            add_issue_note(temp_issues_dir, "BUG-999", "note")

        assert "not found" in str(exc_info.value).lower()
