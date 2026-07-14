"""Tests for unified issue CLI.

Tests all commands: list, create, update, show
"""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from issue_tracker.cli import (
    dispatch_command,
    format_output,
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
title: "{{TITLE}}"
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: BUG
priority: p2
labels: ["bug", "triage"]
related: []
---

## Summary
<!-- Brief description of the bug -->

## Steps to Reproduce
1. <!-- Step 1 -->

## Expected Behavior
<!-- What should happen -->

## Actual Behavior
<!-- What actually happens -->
""")

    # Create feature template
    (issues_dir / "templates" / "feature_request.md").write_text("""---
id: {{ID}}
title: "{{TITLE}}"
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: FEAT
priority: p2
labels: ["enhancement", "triage"]
related: []
---

## Summary
<!-- Brief description of the feature -->
""")

    # Create UI template
    (issues_dir / "templates" / "ui_regression.md").write_text("""---
id: {{ID}}
title: "{{TITLE}}"
created: {{DATE}}
status: {{STATUS}}
author: {{AUTHOR}}
type: UI
priority: p2
labels: ["ui-regression", "visual", "triage"]
related: []
---

## Summary
<!-- Brief description of the visual issue -->

## Component

## Visual Issue
""")

    # Create counters file
    (issues_dir / "counters.json").write_text('{"BUG": 0, "FEAT": 0, "UI": 0}')

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
    (temp_issues_dir / "counters.json").write_text('{"BUG": 1, "FEAT": 1, "UI": 0}')

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

    def test_version_flag(self, capsys):
        """issue --version reports the tool version and exits 0."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert any(ch.isdigit() for ch in captured.out)

    def test_description_sources_are_mutually_exclusive(self, capsys):
        """-d and --body-file cannot be combined."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["create", "bug", "Title", "-d", "text", "--body-file", "b.md"])
        assert exc_info.value.code == 2

    def test_template_command(self):
        """Test parsing template command."""
        args = parse_args(["template", "bug"])
        assert args.command == "template"
        assert args.type == "bug"


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


class TestListOrdering:
    """Tests for the ordering of issues in human-readable list output."""

    def _ids_in_order(self, output: str, prefix: str) -> list[int]:
        """Return the numeric IDs for a given prefix in the order they appear."""
        return [int(m) for m in re.findall(rf"#{prefix}-(\d+)", output)]

    def _feat(self, num: int, priority: str, status: str = "open") -> dict:
        return {
            "id": f"FEAT-{num:03d}",
            "type": "FEAT",
            "status": status,
            "priority": priority,
            "title": "t",
        }

    def test_default_sorts_by_priority_then_id(self):
        """Default: higher priority first, ID ascending as tie-breaker."""
        issues = [
            self._feat(200, "p1"),
            self._feat(7, "p3"),
            self._feat(55, "p2"),
            self._feat(132, "p3"),
            self._feat(40, "p1"),
        ]
        output = format_output(issues, no_color=True)
        # p1: 40, 200 -> p2: 55 -> p3: 7, 132
        assert self._ids_in_order(output, "FEAT") == [40, 200, 55, 7, 132]

    def test_sort_id_gives_ascending_ids(self):
        """--sort id ignores priority and reads as a clean ascending list."""
        issues = [
            self._feat(200, "p1"),
            self._feat(7, "p3"),
            self._feat(55, "p2"),
            self._feat(132, "p3"),
        ]
        output = format_output(issues, no_color=True, sort_by="id")
        assert self._ids_in_order(output, "FEAT") == [7, 55, 132, 200]

    def test_sort_status_groups_actionable_first(self):
        """--sort status puts open/in_progress before resolved."""
        issues = [
            self._feat(50, "p1", status="resolved"),
            self._feat(10, "p2", status="open"),
            self._feat(30, "p2", status="in_progress"),
        ]
        output = format_output(issues, no_color=True, sort_by="status")
        assert self._ids_in_order(output, "FEAT") == [10, 30, 50]

    def test_list_command_accepts_sort_flag(self, sample_active_issues, capsys):
        """The list command exposes --sort end-to-end."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "list", "--sort", "id"]),
        ):
            main()
        captured = capsys.readouterr()
        assert "BUG-001" in captured.out


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

    def test_create_description_from_stdin(self, temp_issues_dir, capsys):
        """-d - reads the description from stdin, avoiding shell quoting."""
        long_text = 'line1\nline2 with "quotes" and `backticks`\nline3'
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "create", "bug", "Stdin bug", "-d", "-"]),
            patch("sys.stdin", io.StringIO(long_text)),
        ):
            main()

        content = (temp_issues_dir / "active" / "BUG-001.md").read_text()
        assert 'line2 with "quotes" and `backticks`' in content

    def test_create_description_from_file(self, temp_issues_dir, capsys):
        """--description-file loads the description from a file."""
        desc_file = temp_issues_dir.parent / "desc.md"
        desc_file.write_text("Description loaded from file.")
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch(
                "sys.argv",
                [
                    "issue",
                    "create",
                    "bug",
                    "File bug",
                    "--description-file",
                    str(desc_file),
                ],
            ),
        ):
            main()

        content = (temp_issues_dir / "active" / "BUG-001.md").read_text()
        assert "Description loaded from file." in content

    def test_create_body_from_file(self, temp_issues_dir, capsys):
        """--body-file replaces the whole body; frontmatter stays tool-owned."""
        body_file = temp_issues_dir.parent / "body.md"
        body_file.write_text(
            "## Summary\nFull custom body.\n\n## Root Cause\nDetails here.\n"
        )
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch(
                "sys.argv",
                [
                    "issue",
                    "create",
                    "bug",
                    "Body bug",
                    "--body-file",
                    str(body_file),
                ],
            ),
        ):
            main()

        content = (temp_issues_dir / "active" / "BUG-001.md").read_text()
        assert "id: BUG-001" in content
        assert "## Root Cause" in content
        assert "<!--" not in content, "template skeleton must not leak into body"

    def test_create_body_from_stdin(self, temp_issues_dir, capsys):
        """--body-file - reads the body from stdin for piping workflows."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch(
                "sys.argv",
                ["issue", "create", "feat", "Piped feat", "--body-file", "-"],
            ),
            patch("sys.stdin", io.StringIO("## Summary\nPiped body.\n")),
        ):
            main()

        content = (temp_issues_dir / "active" / "FEAT-001.md").read_text()
        assert "Piped body." in content

    def test_create_json_output(self, temp_issues_dir, capsys):
        """create --json emits machine-readable result on stdout."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch(
                "sys.argv",
                ["issue", "create", "bug", "JSON bug", "-p", "p1", "--json"],
            ),
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["id"] == "BUG-001"
        assert data["status"] == "open"
        assert data["priority"] == "p1"
        assert data["file"].endswith("BUG-001.md")


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

    def test_update_json_output(self, sample_active_issues, capsys):
        """update --json emits machine-readable result on stdout."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "update", "BUG-001", "resolved", "--json"]),
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["id"] == "BUG-001"
        assert data["status"] == "resolved"
        assert data["file"].endswith("BUG-001.md")

    def test_update_with_note_appends_to_body(self, sample_active_issues, capsys):
        """--note appends the note text to the ticket body during update."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch(
                "sys.argv",
                [
                    "issue",
                    "update",
                    "BUG-001",
                    "resolved",
                    "--note",
                    "Fixed by clamping the index.",
                ],
            ),
        ):
            assert main() == 0

        content = (sample_active_issues / "resolved" / "BUG-001.md").read_text()
        assert "Fixed by clamping the index." in content
        assert "## Note" in content

    def test_update_with_note_file(self, sample_active_issues, tmp_path, capsys):
        """--note-file reads the note from a file and appends it."""
        note_file = tmp_path / "note.md"
        note_file.write_text("Resolution details from a file.")
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch(
                "sys.argv",
                [
                    "issue",
                    "update",
                    "BUG-001",
                    "resolved",
                    "--note-file",
                    str(note_file),
                ],
            ),
        ):
            assert main() == 0

        content = (sample_active_issues / "resolved" / "BUG-001.md").read_text()
        assert "Resolution details from a file." in content

    def test_update_note_from_stdin(self, sample_active_issues, capsys):
        """--note - reads the note text from stdin."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.stdin", io.StringIO("Piped resolution note.")),
            patch(
                "sys.argv",
                ["issue", "update", "BUG-001", "resolved", "--note", "-"],
            ),
        ):
            assert main() == 0

        content = (sample_active_issues / "resolved" / "BUG-001.md").read_text()
        assert "Piped resolution note." in content

    def test_update_note_sources_are_mutually_exclusive(self, capsys):
        """--note and --note-file cannot be combined."""
        with pytest.raises(SystemExit):
            parse_args(
                ["update", "BUG-001", "resolved", "--note", "x", "--note-file", "n.md"]
            )


class TestNoteCommand:
    """Tests for the standalone 'note' command (no status change)."""

    def test_note_appends_without_status_change(self, sample_active_issues, capsys):
        """`issue note` records a note and keeps the issue where it is."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch(
                "sys.argv",
                ["issue", "note", "BUG-001", "Progress update: root cause found."],
            ),
        ):
            assert main() == 0

        # Still active, note present, status untouched
        active_file = sample_active_issues / "active" / "BUG-001.md"
        assert active_file.exists()
        content = active_file.read_text()
        assert "Progress update: root cause found." in content
        assert "## Note" in content

    def test_note_from_file(self, sample_active_issues, tmp_path, capsys):
        """`issue note --note-file` reads the note from a file."""
        note_file = tmp_path / "n.md"
        note_file.write_text("Detailed note from file.")
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch(
                "sys.argv",
                ["issue", "note", "BUG-001", "--note-file", str(note_file)],
            ),
        ):
            assert main() == 0

        content = (sample_active_issues / "active" / "BUG-001.md").read_text()
        assert "Detailed note from file." in content

    def test_note_from_stdin(self, sample_active_issues, capsys):
        """`issue note BUG-001 -` reads the note from stdin."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.stdin", io.StringIO("Piped standalone note.")),
            patch("sys.argv", ["issue", "note", "BUG-001", "-"]),
        ):
            assert main() == 0

        content = (sample_active_issues / "active" / "BUG-001.md").read_text()
        assert "Piped standalone note." in content

    def test_note_json_output(self, sample_active_issues, capsys):
        """`issue note --json` emits a machine-readable result."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch(
                "sys.argv",
                ["issue", "note", "BUG-001", "A note", "--json"],
            ),
        ):
            assert main() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["id"] == "BUG-001"
        assert data["file"].endswith("BUG-001.md")

    def test_note_missing_text_errors(self, sample_active_issues, capsys):
        """`issue note` with no text and no --note-file is an operation error."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "note", "BUG-001"]),
        ):
            assert main() == 1

    def test_note_missing_issue_errors(self, sample_active_issues, capsys):
        """Noting a non-existent issue returns exit code 1."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "note", "NOPE-999", "text"]),
        ):
            assert main() == 1

    def test_note_conflicting_sources_are_usage_error(self, capsys):
        """Text and --note-file together is a usage error (exit 2), matching
        the mutual-exclusion behavior of `update --note/--note-file`."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["note", "BUG-001", "some text", "--note-file", "n.md"])
        assert exc_info.value.code == 2


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

    def test_show_json_includes_body(self, sample_active_issues, capsys):
        """show --json returns the complete issue: frontmatter plus body."""
        with (
            patch(
                "issue_tracker.cli.find_issues_dir", return_value=sample_active_issues
            ),
            patch("sys.argv", ["issue", "show", "BUG-001", "--json"]),
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["id"] == "BUG-001"
        assert "App crashes on startup." in data["body"]


class TestTemplateCommand:
    """Tests for the template command (agent fills it, pipes to --body-file)."""

    def test_template_prints_body_skeleton(self, temp_issues_dir, capsys):
        """issue template <type> prints the template body without frontmatter."""
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "template", "bug"]),
        ):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "## Summary" in captured.out
        assert "## Steps to Reproduce" in captured.out
        # Frontmatter is tool-owned: must not be part of the fillable skeleton
        assert "id: {{ID}}" not in captured.out
        assert not captured.out.startswith("---")

    def test_template_missing_file(self, temp_issues_dir, capsys):
        """Missing per-repo template file is a clear error, not a crash."""
        (temp_issues_dir / "templates" / "bug_report.md").unlink()
        with (
            patch("issue_tracker.cli.find_issues_dir", return_value=temp_issues_dir),
            patch("sys.argv", ["issue", "template", "bug"]),
        ):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "template" in captured.err.lower()


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
