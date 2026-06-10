"""BDD tests for automatic color detection in issues CLI.

Tests the should_disable_color() function which determines whether
ANSI color codes should be emitted based on terminal environment.

Behavior:
- NO_COLOR env var (any value) disables color
- Non-TTY stdout (pipe/redirect) disables color
- Otherwise, color is enabled
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestShouldDisableColor:
    """Test suite for should_disable_color() behavior."""

    def test_disables_color_when_no_color_env_set(self) -> None:
        """NO_COLOR environment variable disables color output."""
        from issue_tracker.cli import should_disable_color

        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert should_disable_color() is True

    def test_disables_color_when_no_color_env_empty(self) -> None:
        """NO_COLOR being present (even empty) disables color.

        Per no-color.org standard, the presence of the variable matters,
        not its value.
        """
        from issue_tracker.cli import should_disable_color

        with patch.dict(os.environ, {"NO_COLOR": ""}, clear=False):
            assert should_disable_color() is True

    def test_disables_color_when_stdout_not_tty(self) -> None:
        """Non-TTY stdout (pipe/redirect) disables color."""
        from issue_tracker.cli import should_disable_color

        with (
            patch.object(sys.stdout, "isatty", return_value=False),
            patch.dict(os.environ, {}, clear=False),
        ):
            assert should_disable_color() is True

    def test_enables_color_when_tty_and_no_color_unset(self) -> None:
        """Color enabled when TTY and NO_COLOR not set."""
        from issue_tracker.cli import should_disable_color

        with (
            patch.object(sys.stdout, "isatty", return_value=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            # Remove NO_COLOR if it exists in current environment
            os.environ.pop("NO_COLOR", None)
            assert should_disable_color() is False

    def test_no_color_takes_precedence_over_tty(self) -> None:
        """NO_COLOR disables color even when stdout is TTY."""
        from issue_tracker.cli import should_disable_color

        with (
            patch.object(sys.stdout, "isatty", return_value=True),
            patch.dict(os.environ, {"NO_COLOR": "1"}),
        ):
            assert should_disable_color() is True


class TestFormatOutputColorIntegration:
    """Integration tests for format_output with color detection."""

    def test_format_output_respects_no_color_true(self) -> None:
        """format_output with no_color=True strips ANSI codes."""
        from issue_tracker.cli import format_output

        issues = [
            {
                "id": "BUG-001",
                "title": "Test bug",
                "type": "BUG",
                "status": "open",
                "labels": [],
                "blocked_by": [],
            }
        ]

        output = format_output(issues, no_color=True)
        # Should not contain ANSI escape sequences
        assert "\033[" not in output
        assert "BUG-001" in output

    def test_format_output_with_color_includes_ansi(self) -> None:
        """format_output with no_color=False includes ANSI codes."""
        from issue_tracker.cli import format_output

        issues = [
            {
                "id": "BUG-001",
                "title": "Test bug",
                "type": "BUG",
                "status": "open",
                "labels": [],
                "blocked_by": [],
            }
        ]

        output = format_output(issues, no_color=False)
        # Should contain ANSI escape sequences for color
        assert "\033[" in output


class TestCmdListAutoColor:
    """Test cmd_list uses automatic color detection."""

    def test_cmd_list_no_color_env(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_list disables color when NO_COLOR is set."""
        from issue_tracker.cli import cmd_list, parse_args

        active_dir = tmp_path / "active"
        active_dir.mkdir()
        (active_dir / "BUG-001.md").write_text(
            "---\nid: BUG-001\ntype: BUG\nstatus: open\ntitle: Test\npriority: p2\nlabels: []\nblocked_by: []\n---\n"
        )

        args = parse_args(["list"])

        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            result = cmd_list(args, tmp_path)

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out
        assert "BUG-001" in captured.out

    def test_cmd_list_non_tty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_list disables color when stdout is not a TTY."""
        from issue_tracker.cli import cmd_list, parse_args

        active_dir = tmp_path / "active"
        active_dir.mkdir()
        (active_dir / "BUG-001.md").write_text(
            "---\nid: BUG-001\ntype: BUG\nstatus: open\ntitle: Test\npriority: p2\nlabels: []\nblocked_by: []\n---\n"
        )

        args = parse_args(["list"])

        with (
            patch.object(sys.stdout, "isatty", return_value=False),
            patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("NO_COLOR", None)
            result = cmd_list(args, tmp_path)

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" not in captured.out

    def test_cmd_list_tty_with_color(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_list enables color when TTY and NO_COLOR not set."""
        from issue_tracker.cli import cmd_list, parse_args

        active_dir = tmp_path / "active"
        active_dir.mkdir()
        (active_dir / "BUG-001.md").write_text(
            "---\nid: BUG-001\ntype: BUG\nstatus: open\ntitle: Test\npriority: p2\nlabels: []\nblocked_by: []\n---\n"
        )

        args = parse_args(["list"])

        with (
            patch.object(sys.stdout, "isatty", return_value=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            os.environ.pop("NO_COLOR", None)
            result = cmd_list(args, tmp_path)

        assert result == 0
        captured = capsys.readouterr()
        assert "\033[" in captured.out


class TestSearchJsonOutput:
    """Test --json flag on search command."""

    def test_search_json_outputs_empty_array(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """search --json outputs empty array when no matches."""
        from issue_tracker.cli import cmd_search, parse_args

        active_dir = tmp_path / "active"
        active_dir.mkdir()
        (active_dir / "BUG-001.md").write_text(
            "---\nid: BUG-001\ntype: BUG\nstatus: open\ntitle: Some bug\npriority: p2\nlabels: []\nblocked_by: []\n---\n"
        )

        args = parse_args(["search", "nonexistent", "--json"])
        result = cmd_search(args, tmp_path)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == []

    def test_search_json_outputs_matching_issues(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """search --json outputs array of matching issues."""
        from issue_tracker.cli import cmd_search, parse_args

        active_dir = tmp_path / "active"
        active_dir.mkdir()
        (active_dir / "BUG-001.md").write_text(
            "---\nid: BUG-001\ntype: BUG\nstatus: open\ntitle: Fix crash bug\npriority: p2\nlabels: []\nblocked_by: []\n---\nBody mentions crash.\n"
        )
        (active_dir / "FEAT-001.md").write_text(
            "---\nid: FEAT-001\ntype: FEAT\nstatus: open\ntitle: New feature\npriority: p2\nlabels: []\nblocked_by: []\n---\nNo keyword here.\n"
        )

        args = parse_args(["search", "crash", "--json"])
        result = cmd_search(args, tmp_path)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["id"] == "BUG-001"
        assert "crash" in data[0]["title"].lower()


class TestStatsJsonOutput:
    """Test --json flag on stats command."""

    def test_stats_json_outputs_structured(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """stats --json outputs structured statistics."""
        from issue_tracker.cli import cmd_stats, parse_args

        active_dir = tmp_path / "active"
        resolved_dir = tmp_path / "resolved"
        active_dir.mkdir()
        resolved_dir.mkdir()

        (active_dir / "BUG-001.md").write_text(
            "---\nid: BUG-001\ntype: BUG\nstatus: open\ntitle: Bug 1\npriority: p0\nlabels: []\nblocked_by: []\n---\n"
        )
        (active_dir / "BUG-002.md").write_text(
            "---\nid: BUG-002\ntype: BUG\nstatus: in_progress\ntitle: Bug 2\npriority: p1\nlabels: []\nblocked_by: []\n---\n"
        )
        (resolved_dir / "FEAT-001.md").write_text(
            "---\nid: FEAT-001\ntype: FEAT\nstatus: resolved\ntitle: Feature 1\npriority: p2\nlabels: []\nblocked_by: []\n---\n"
        )

        args = parse_args(["stats", "--json"])
        result = cmd_stats(args, tmp_path)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total"] == 3
        assert data["active"] == 2
        assert data["resolved"] == 1
        assert "by_type" in data
        assert data["by_type"]["BUG"] == 2
        assert data["by_type"]["FEAT"] == 1
        assert "by_status" in data
        assert "by_priority" in data
