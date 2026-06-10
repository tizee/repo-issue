"""Tests for unified issue CLI.

Tests all commands: list, create, update, show
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from issue_tracker.cli import (
    dispatch_command,
    main,
    parse_args,
)


@pytest.fixture
def temp_issues_dir():
    """Create a temporary issues directory structure."""
    temp_dir = Path(tempfile.mkdtemp())
    issues_dir = temp_dir / "issues"
    issues_dir.mkdir()

    # Create directory structure
    (issues_dir / "active").mkdir()
    (issues_dir / "resolved").mkdir()
    (issues_dir / "templates").mkdir()

    # Create bug report template
    (issues_dir / "templates" / "bug_report.md").write_text("""---
id: {{ID}}
title: {{TITLE}}
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: BUG
labels: ["bug", "triage"]
related: []
---

## Summary
{{DESCRIPTION}}

## Steps to Reproduce
1.

## Expected Behavior

## Actual Behavior
""")

    # Create feature template
    (issues_dir / "templates" / "feature_request.md").write_text("""---
id: {{ID}}
title: {{TITLE}}
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: FEAT
labels: ["enhancement", "triage"]
related: []
---

## Summary
{{DESCRIPTION}}
""")

    # Create UI template
    (issues_dir / "templates" / "ui_regression.md").write_text("""---
id: {{ID}}
title: {{TITLE}}
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: UI
labels: ["ui-regression", "visual", "triage"]
related: []
---

## Summary
{{DESCRIPTION}}

## Component

## Visual Issue
""")

    # Create counters file
    (issues_dir / "counters.json").write_text(
        '{"BUG": 0, "FEAT": 0, "UI": 0, "SAFE": 0, "DOCS": 0}'
    )

    yield issues_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_active_issues(temp_issues_dir):
    """Create sample active issues for testing."""
    active_dir = temp_issues_dir / "active"

    # BUG-001 (open)
    (active_dir / "BUG-001.md").write_text("""---
id: BUG-001
title: "Fix crash on startup"
created: 2024-01-15
status: open
author: agent
type: BUG
labels: ["bug", "critical"]
related: []
---

## Summary
App crashes on startup.

## Steps to Reproduce
1. Launch app
""")

    # FEAT-001 (open)
    (active_dir / "FEAT-001.md").write_text("""---
id: FEAT-001
title: "Add dark mode"
created: 2024-01-14
status: open
author: agent
type: FEAT
labels: ["enhancement"]
related: []
---

## Summary
Add dark mode support.
""")

    # Update counters
    (temp_issues_dir / "counters.json").write_text(
        '{"BUG": 1, "FEAT": 1, "UI": 0, "SAFE": 0, "DOCS": 0}'
    )

    return temp_issues_dir


class TestParseArgs:
    """Tests for argument parsing."""

    def test_list_command_no_args(self):
        """Test parsing list command with no args."""
        args = parse_args(["list"])
        assert args.command == "list"
        assert args.filters == []
        assert not args.all
        assert not args.labels

    def test_list_command_with_filters(self):
        """Test parsing list command with filters."""
        args = parse_args(["list", "bug", "open"])
        assert args.command == "list"
        assert "bug" in args.filters
        assert "open" in args.filters

    def test_list_command_with_all_flag(self):
        """Test parsing list --all."""
        args = parse_args(["list", "--all"])
        assert args.command == "list"
        assert args.all is True

    def test_list_command_with_labels_flag(self):
        """Test parsing list --labels."""
        args = parse_args(["list", "--labels"])
        assert args.command == "list"
        assert args.labels is True

    def test_create_command_bug(self):
        """Test parsing create bug command."""
        args = parse_args(["create", "bug", "Fix crash"])
        assert args.command == "create"
        assert args.type == "bug"
        assert args.title == "Fix crash"

    def test_create_command_feat_with_description(self):
        """Test parsing create feat with --description."""
        args = parse_args(
            ["create", "feat", "Add feature", "--description", "Details here"]
        )
        assert args.command == "create"
        assert args.type == "feat"
        assert args.title == "Add feature"
        assert args.description == "Details here"

    def test_create_command_ui_with_author(self):
        """Test parsing create ui with --author."""
        args = parse_args(["create", "ui", "Button broken", "--author", "user"])
        assert args.command == "create"
        assert args.type == "ui"
        assert args.title == "Button broken"
        assert args.author == "user"

    def test_update_command(self):
        """Test parsing update command."""
        args = parse_args(["update", "BUG-001", "resolved"])
        assert args.command == "update"
        assert args.issue_id == "BUG-001"
        assert args.status == "resolved"

    def test_show_command(self):
        """Test parsing show command."""
        args = parse_args(["show", "FEAT-001"])
        assert args.command == "show"
        assert args.issue_id == "FEAT-001"

    def test_help_flag(self):
        """Test that --help works."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_command_help(self):
        """Test that command-specific help works."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["create", "--help"])
        assert exc_info.value.code == 0


class TestListCommand:
    """Tests for list command integration."""

    def test_list_shows_issues(self, sample_active_issues, capsys):
        """Test that list command displays issues."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "list"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "FEAT-001" in captured.out
        assert "Fix crash" in captured.out
        assert "Add dark mode" in captured.out

    def test_list_with_type_filter(self, sample_active_issues, capsys):
        """Test list with type filter."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "list", "bug"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "FEAT-001" not in captured.out

    def test_list_with_labels_flag(self, sample_active_issues, capsys):
        """Test list --labels."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "list", "--labels"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "bug" in captured.out
        assert "enhancement" in captured.out


class TestCreateCommand:
    """Tests for create command."""

    def test_create_bug_issue(self, temp_issues_dir, capsys):
        """Test creating a bug issue."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "create", "bug", "New Bug"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "Created" in captured.out
        assert "BUG-001" in captured.out

        # Verify file was created
        bug_file = temp_issues_dir / "active" / "BUG-001.md"
        assert bug_file.exists()
        content = bug_file.read_text()
        assert "New Bug" in content
        assert "type: BUG" in content

    def test_create_feat_issue_with_description(self, temp_issues_dir, capsys):
        """Test creating a feature issue with description."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch(
                "sys.argv",
                ["issue", "create", "feat", "New Feature", "-d", "Feature details"],
            ),
        ):
            main()

        captured = capsys.readouterr()
        assert "Created" in captured.out

        feat_file = temp_issues_dir / "active" / "FEAT-001.md"
        assert feat_file.exists()
        content = feat_file.read_text()
        assert "New Feature" in content
        assert "Feature details" in content

    def test_create_ui_issue(self, temp_issues_dir, capsys):
        """Test creating a UI issue."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "create", "ui", "Visual glitch"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "Created" in captured.out

        ui_file = temp_issues_dir / "active" / "UI-001.md"
        assert ui_file.exists()
        content = ui_file.read_text()
        assert "Visual glitch" in content
        assert "type: UI" in content

    def test_create_invalid_type(self, temp_issues_dir, capsys):
        """Test creating with invalid type shows error."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "create", "invalid", "Title"]),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            # argparse returns 2 for invalid choices
            assert exc_info.value.code == 2


class TestUpdateCommand:
    """Tests for update command."""

    def test_update_status_to_resolved(self, sample_active_issues, capsys):
        """Test updating issue status to resolved."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "update", "BUG-001", "resolved"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "Updated" in captured.out
        assert "resolved" in captured.out

        # Verify file moved to resolved
        assert not (sample_active_issues / "active" / "BUG-001.md").exists()
        assert (sample_active_issues / "resolved" / "BUG-001.md").exists()

    def test_update_status_to_in_progress(self, sample_active_issues, capsys):
        """Test updating issue status to in_progress."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "update", "FEAT-001", "in_progress"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "Updated" in captured.out

        # Verify status updated in file
        content = (sample_active_issues / "active" / "FEAT-001.md").read_text()
        assert "status: in_progress" in content

    def test_update_invalid_issue_id(self, sample_active_issues, capsys):
        """Test updating non-existent issue shows error."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "update", "INVALID-999", "resolved"]),
        ):
            result = main()
            assert result == 1

    def test_update_invalid_status(self, sample_active_issues, capsys):
        """Test updating with invalid status shows error."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "update", "BUG-001", "invalid_status"]),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error


class TestShowCommand:
    """Tests for show command."""

    def test_show_issue_details(self, sample_active_issues, capsys):
        """Test showing issue details."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "show", "BUG-001"]),
        ):
            main()

        captured = capsys.readouterr()
        assert "BUG-001" in captured.out
        assert "Fix crash on startup" in captured.out
        assert "App crashes on startup" in captured.out

    def test_show_nonexistent_issue(self, sample_active_issues, capsys):
        """Test showing non-existent issue shows error."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "show", "INVALID-999"]),
        ):
            result = main()
            assert result == 1


class TestCommandDispatch:
    """Tests for command dispatch logic."""

    def test_dispatch_list(self):
        """Test dispatch to list command."""
        args = MagicMock()
        args.command = "list"
        args.filters = []
        args.all = False
        args.labels = False

        with patch("issue_tracker.cli.cmd_list") as mock_list:
            dispatch_command(args, Path("/tmp"))
            mock_list.assert_called_once()

    def test_dispatch_create(self):
        """Test dispatch to create command."""
        args = MagicMock()
        args.command = "create"
        args.type = "bug"
        args.title = "Title"
        args.description = None
        args.author = "agent"

        with patch("issue_tracker.cli.cmd_create") as mock_create:
            dispatch_command(args, Path("/tmp"))
            mock_create.assert_called_once()

    def test_dispatch_update(self):
        """Test dispatch to update command."""
        args = MagicMock()
        args.command = "update"
        args.issue_id = "BUG-001"
        args.status = "resolved"

        with patch("issue_tracker.cli.cmd_update") as mock_update:
            dispatch_command(args, Path("/tmp"))
            mock_update.assert_called_once()

    def test_dispatch_show(self):
        """Test dispatch to show command."""
        args = MagicMock()
        args.command = "show"
        args.issue_id = "BUG-001"

        with patch("issue_tracker.cli.cmd_show") as mock_show:
            dispatch_command(args, Path("/tmp"))
            mock_show.assert_called_once()

    def test_dispatch_unknown_command(self):
        """Test dispatch with unknown command shows error."""
        args = MagicMock()
        args.command = "unknown"

        result = dispatch_command(args, Path("/tmp"))
        assert result == 1
