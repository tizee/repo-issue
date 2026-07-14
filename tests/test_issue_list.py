"""Tests for issue list command functionality."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from issue_tracker.cli import (
    filter_issues,
    format_output,
    get_all_labels,
    load_issues,
    main,
    parse_args,
)


@pytest.fixture
def temp_issues_dir():
    """Create a temporary directory with sample issues for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    active_dir = temp_dir / "active"
    active_dir.mkdir(parents=True)

    # Create BUG-001 (open)
    (active_dir / "BUG-001.md").write_text("""---
id: BUG-001
title: "Fix crash on null pointer"
created: 2024-01-15
status: open
author: agent
type: BUG
labels: ["bug", "critical"]
related: []
---

## Summary
Fix the null pointer crash.
""")

    # Create BUG-002 (in_progress)
    (active_dir / "BUG-002.md").write_text("""---
id: BUG-002
title: "Memory leak in image handler"
created: 2024-01-18
status: in_progress
author: agent
type: BUG
labels: ["bug", "memory"]
related: []
---

## Summary
Fix memory leak.
""")

    # Create FEAT-001 (open)
    (active_dir / "FEAT-001.md").write_text("""---
id: FEAT-001
title: "Add dirty file detection"
created: 2024-01-14
status: open
author: agent
type: FEAT
labels: ["enhancement", "triage"]
related: []
---

## Summary
Add dirty file detection feature.
""")

    # Create FEAT-002 (open)
    (active_dir / "FEAT-002.md").write_text("""---
id: FEAT-002
title: "Compact session workflow"
created: 2024-01-19
status: open
author: agent
type: FEAT
labels: ["enhancement", "ux"]
related: []
---

## Summary
Compact session workflow.
""")

    # Create UI-001 (open)
    (active_dir / "UI-001.md").write_text("""---
id: UI-001
title: "Status line context not rendering"
created: 2024-01-20
status: open
author: agent
type: UI
labels: ["ui-regression", "visual"]
related: []
---

## Summary
Fix status line rendering.
""")

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def empty_issues_dir():
    """Create an empty issues directory."""
    temp_dir = Path(tempfile.mkdtemp())
    active_dir = temp_dir / "active"
    active_dir.mkdir(parents=True)
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def missing_issues_dir():
    """Create a temp directory without issues structure."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


class TestParseArgs:
    """Tests for argument parsing."""

    def test_no_args_defaults_to_help(self):
        """Test that no arguments results in no command."""
        args = parse_args([])
        assert args.command is None

    def test_list_with_labels_flag(self):
        """Test ./issue list --labels."""
        args = parse_args(["list", "--labels"])
        assert args.command == "list"
        assert args.labels is True

    def test_filter_by_type_shorthand(self):
        """Test type shorthand like 'bug', 'feat', 'ui'."""
        args = parse_args(["list", "bug"])
        assert "bug" in args.filters

    def test_filter_by_status_shorthand(self):
        """Test status shorthand like 'open', 'in_progress'."""
        args = parse_args(["list", "open"])
        assert "open" in args.filters

    def test_explicit_type_filter(self):
        """Test explicit type: prefix."""
        args = parse_args(["list", "type:FEAT"])
        assert "type:FEAT" in args.filters

    def test_explicit_status_filter(self):
        """Test explicit status: prefix."""
        args = parse_args(["list", "status:open"])
        assert "status:open" in args.filters

    def test_label_filter(self):
        """Test label: prefix filter."""
        args = parse_args(["list", "label:enhancement"])
        assert "label:enhancement" in args.filters

    def test_multiple_filters(self):
        """Test combining multiple filters."""
        args = parse_args(["list", "bug", "open", "label:critical"])
        assert len(args.filters) == 3
        assert "bug" in args.filters
        assert "open" in args.filters
        assert "label:critical" in args.filters


class TestLoadIssues:
    """Tests for loading issues from files."""

    def test_load_all_active_issues(self, temp_issues_dir):
        """Test loading all issues from active directory."""
        issues = load_issues(temp_issues_dir)
        assert len(issues) == 5
        ids = {issue["id"] for issue in issues}
        assert ids == {"BUG-001", "BUG-002", "FEAT-001", "FEAT-002", "UI-001"}

    def test_issue_structure(self, temp_issues_dir):
        """Test that loaded issues have correct structure."""
        issues = load_issues(temp_issues_dir)
        bug_001 = next(i for i in issues if i["id"] == "BUG-001")

        assert bug_001["title"] == "Fix crash on null pointer"
        assert bug_001["status"] == "open"
        assert bug_001["type"] == "BUG"
        assert bug_001["created"] == "2024-01-15"
        assert bug_001["labels"] == ["bug", "critical"]

    def test_load_empty_directory(self, empty_issues_dir):
        """Test loading from empty directory."""
        issues = load_issues(empty_issues_dir)
        assert issues == []

    def test_skip_non_yaml_files(self, temp_issues_dir):
        """Test that non-markdown files are skipped."""
        # Create a non-markdown file
        (temp_issues_dir / "active" / "README.txt").write_text("not an issue")

        issues = load_issues(temp_issues_dir)
        assert len(issues) == 5  # Still only 5 valid issues

    def test_skip_invalid_yaml(self, temp_issues_dir):
        """Test that files with invalid YAML are skipped."""
        (temp_issues_dir / "active" / "INVALID-001.md").write_text("""---
not valid yaml: [
---
content
""")

        issues = load_issues(temp_issues_dir)
        # Should still load valid issues
        assert len(issues) == 5


class TestFilterIssues:
    """Tests for issue filtering."""

    @pytest.fixture
    def sample_issues(self):
        """Sample issues for filtering tests."""
        return [
            {"id": "BUG-001", "type": "BUG", "status": "open", "labels": ["critical"]},
            {
                "id": "BUG-002",
                "type": "BUG",
                "status": "in_progress",
                "labels": ["memory"],
            },
            {
                "id": "FEAT-001",
                "type": "FEAT",
                "status": "open",
                "labels": ["enhancement"],
            },
            {"id": "UI-001", "type": "UI", "status": "open", "labels": ["visual"]},
        ]

    def test_no_filters_returns_all(self, sample_issues):
        """Test that no filters returns all issues."""
        result = filter_issues(sample_issues, [])
        assert len(result) == 4

    def test_filter_by_type(self, sample_issues):
        """Test filtering by type."""
        result = filter_issues(sample_issues, ["type:BUG"])
        assert len(result) == 2
        assert all(i["type"] == "BUG" for i in result)

    def test_filter_by_type_shorthand(self, sample_issues):
        """Test type shorthand filter."""
        result = filter_issues(sample_issues, ["feat"])
        assert len(result) == 1
        assert result[0]["id"] == "FEAT-001"

    def test_filter_by_status(self, sample_issues):
        """Test filtering by status."""
        result = filter_issues(sample_issues, ["status:open"])
        assert len(result) == 3
        assert all(i["status"] == "open" for i in result)

    def test_filter_by_status_shorthand(self, sample_issues):
        """Test status shorthand filter."""
        result = filter_issues(sample_issues, ["open"])
        assert len(result) == 3

    def test_filter_by_label(self, sample_issues):
        """Test filtering by exact label match."""
        result = filter_issues(sample_issues, ["label:critical"])
        assert len(result) == 1
        assert result[0]["id"] == "BUG-001"

    def test_filter_by_label_partial_match(self, sample_issues):
        """Test filtering by partial label match."""
        result = filter_issues(sample_issues, ["label:crit"])
        assert len(result) == 1
        assert result[0]["id"] == "BUG-001"

    def test_filter_by_nonexistent_label(self, sample_issues):
        """Test filtering by label that doesn't exist."""
        result = filter_issues(sample_issues, ["label:nonexistent"])
        assert len(result) == 0

    def test_multiple_filters_and_logic(self, sample_issues):
        """Test that multiple filters combine with AND logic."""
        result = filter_issues(sample_issues, ["bug", "open"])
        assert len(result) == 1
        assert result[0]["id"] == "BUG-001"

    def test_filter_resolved_status(self, sample_issues):
        """Test filtering by resolved status."""
        issues_with_resolved = sample_issues + [
            {"id": "BUG-003", "type": "BUG", "status": "resolved", "labels": []}
        ]
        result = filter_issues(issues_with_resolved, ["resolved"])
        assert len(result) == 1
        assert result[0]["id"] == "BUG-003"


class TestGetAllLabels:
    """Tests for label aggregation."""

    def test_collects_all_unique_labels(self):
        """Test that all unique labels are collected."""
        issues = [
            {"id": "BUG-001", "labels": ["critical", "bug"]},
            {"id": "FEAT-001", "labels": ["enhancement", "triage"]},
            {"id": "UI-001", "labels": ["visual", "triage"]},  # triage repeated
        ]

        labels = get_all_labels(issues)

        assert len(labels) == 5
        assert set(labels.keys()) == {
            "critical",
            "bug",
            "enhancement",
            "triage",
            "visual",
        }

    def test_counts_label_usage(self):
        """Test that label usage is counted correctly."""
        issues = [
            {"id": "BUG-001", "labels": ["critical"]},
            {"id": "BUG-002", "labels": ["critical"]},
            {"id": "FEAT-001", "labels": ["critical"]},
        ]

        labels = get_all_labels(issues)

        assert labels["critical"] == 3

    def test_empty_issues_returns_empty(self):
        """Test that empty issues list returns empty labels."""
        labels = get_all_labels([])
        assert labels == {}

    def test_issues_without_labels(self):
        """Test handling of issues without labels field."""
        issues = [
            {"id": "BUG-001", "labels": ["bug"]},
            {"id": "BUG-002"},  # No labels field
            {"id": "BUG-003", "labels": []},  # Empty labels
        ]

        labels = get_all_labels(issues)

        assert labels == {"bug": 1}


class TestFormatOutput:
    """Tests for output formatting."""

    @pytest.fixture
    def sample_issues_for_format(self):
        """Sample issues for formatting tests."""
        return [
            {
                "id": "BUG-001",
                "type": "BUG",
                "status": "open",
                "title": "Fix crash",
                "created": "2024-01-15",
                "labels": ["critical"],
            },
            {
                "id": "BUG-002",
                "type": "BUG",
                "status": "in_progress",
                "title": "Memory leak",
                "created": "2024-01-18",
                "labels": [],
            },
            {
                "id": "FEAT-001",
                "type": "FEAT",
                "status": "open",
                "title": "Add feature",
                "created": "2024-01-14",
                "labels": ["enhancement"],
            },
        ]

    def test_groups_by_type(self, sample_issues_for_format):
        """Test that output is grouped by type."""
        output = format_output(sample_issues_for_format, no_color=True)

        lines = output.split("\n")
        type_headers = [
            ln for ln in lines if ln.startswith("BUG") or ln.startswith("FEAT")
        ]

        assert len(type_headers) == 2
        assert any("BUG" in h for h in type_headers)
        assert any("FEAT" in h for h in type_headers)

    def test_shows_issue_details(self, sample_issues_for_format):
        """Test that issue details are displayed."""
        output = format_output(sample_issues_for_format, no_color=True)

        assert "BUG-001" in output
        assert "Fix crash" in output
        assert "open" in output.lower()

    def test_handles_empty_issues(self):
        """Test formatting with empty issues list."""
        output = format_output([], no_color=True)

        assert "no issues" in output.lower()

    def test_groups_by_status_within_type(self, sample_issues_for_format):
        """Test that issues are grouped by status within each type."""
        output = format_output(sample_issues_for_format, no_color=True)

        # Find BUG section
        lines = output.split("\n")
        bug_section_start = next(
            i for i, ln in enumerate(lines) if ln.startswith("BUG")
        )

        # Both BUG issues should appear in the BUG section
        bug_lines = lines[bug_section_start : bug_section_start + 5]
        bug_section = "\n".join(bug_lines)

        assert "BUG-001" in bug_section
        assert "BUG-002" in bug_section

    def test_sorts_issues_by_numeric_id_ascending(self):
        """Test that issues are sorted by numeric ID in ascending order."""
        issues = [
            {
                "id": "FEAT-100",
                "type": "FEAT",
                "status": "open",
                "title": "Issue 100",
                "created": "2024-01-15",
                "labels": [],
            },
            {
                "id": "FEAT-093",
                "type": "FEAT",
                "status": "open",
                "title": "Issue 93",
                "created": "2024-01-15",
                "labels": [],
            },
            {
                "id": "FEAT-121",
                "type": "FEAT",
                "status": "open",
                "title": "Issue 121",
                "created": "2024-01-15",
                "labels": [],
            },
            {
                "id": "FEAT-048",
                "type": "FEAT",
                "status": "open",
                "title": "Issue 48",
                "created": "2024-01-15",
                "labels": [],
            },
        ]
        output = format_output(issues, no_color=True)

        pos_048 = output.find("FEAT-048")
        pos_093 = output.find("FEAT-093")
        pos_100 = output.find("FEAT-100")
        pos_121 = output.find("FEAT-121")

        assert pos_048 < pos_093 < pos_100 < pos_121

    def test_sorts_issues_across_different_statuses(self):
        """--sort status groups by status first, then by numeric ID."""
        issues = [
            {
                "id": "FEAT-100",
                "type": "FEAT",
                "status": "in_progress",
                "title": "In Progress 100",
                "labels": [],
            },
            {
                "id": "FEAT-093",
                "type": "FEAT",
                "status": "open",
                "title": "Open 93",
                "labels": [],
            },
            {
                "id": "FEAT-121",
                "type": "FEAT",
                "status": "open",
                "title": "Open 121",
                "labels": [],
            },
            {
                "id": "FEAT-048",
                "type": "FEAT",
                "status": "in_progress",
                "title": "In Progress 48",
                "labels": [],
            },
        ]
        output = format_output(issues, no_color=True, sort_by="status")

        pos_open_093 = output.find("Open 93")
        pos_open_121 = output.find("Open 121")
        pos_inprog_048 = output.find("In Progress 48")
        pos_inprog_100 = output.find("In Progress 100")

        assert pos_open_093 < pos_open_121, "Open issues not sorted by ID"
        assert pos_inprog_048 < pos_inprog_100, "In-progress issues not sorted by ID"
        assert pos_open_121 < pos_inprog_048, (
            "Open issues should come before in_progress"
        )


class TestMain:
    """Integration tests for the main function."""

    def test_list_all_active_issues(self, temp_issues_dir, capsys):
        """Test main function lists all active issues."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "list"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "FEAT-001" in captured.out
        assert "UI-001" in captured.out

    def test_list_with_type_filter(self, temp_issues_dir, capsys):
        """Test main function with type filter."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "list", "bug"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "BUG-002" in captured.out
        assert "FEAT-001" not in captured.out
        assert "UI-001" not in captured.out

    def test_list_with_status_filter(self, temp_issues_dir, capsys):
        """Test main function with status filter."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "list", "open"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "BUG-002" not in captured.out  # in_progress
        assert "FEAT-001" in captured.out

    def test_list_labels(self, temp_issues_dir, capsys):
        """Test main function with --labels flag."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "list", "--labels"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "bug" in captured.out
        assert "critical" in captured.out
        assert "enhancement" in captured.out

    def test_no_issues_message(self, empty_issues_dir, capsys):
        """Test message when no issues exist."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=empty_issues_dir),
            patch("sys.argv", ["issue", "list"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "no issues" in captured.out.lower() or captured.out.strip() == ""
