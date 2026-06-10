"""BDD tests for issues/ directory discovery.

Behavior: the CLI finds the repo-local issues/ data directory by walking
up from the current working directory, like git finds .git/. When no
directory is found, it fails fast with a hint to run 'issue init'.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from issue_tracker.discovery import (
    IssuesDirNotFoundError,
    find_issues_dir,
    looks_like_issues_dir,
)


def _make_issues_dir(root: Path) -> Path:
    issues = root / "issues"
    (issues / "active").mkdir(parents=True)
    return issues


class TestFindIssuesDir:
    def test_finds_issues_dir_in_cwd(self, tmp_path):
        """issues/ directly under the start directory is found."""
        issues = _make_issues_dir(tmp_path)
        assert find_issues_dir(tmp_path) == issues

    def test_finds_issues_dir_walking_up(self, tmp_path):
        """issues/ in an ancestor directory is found from a deep subdir."""
        issues = _make_issues_dir(tmp_path)
        deep = tmp_path / "src" / "app" / "module"
        deep.mkdir(parents=True)
        assert find_issues_dir(deep) == issues

    def test_finds_when_started_inside_issues_dir(self, tmp_path):
        """Running from inside issues/ itself resolves to that directory."""
        issues = _make_issues_dir(tmp_path)
        assert find_issues_dir(issues) == issues

    def test_fails_fast_when_no_issues_dir(self, tmp_path):
        """No silent default: missing issues/ raises with an init hint."""
        with pytest.raises(IssuesDirNotFoundError, match="issue init"):
            find_issues_dir(tmp_path)

    def test_ignores_unrelated_issues_directory(self, tmp_path):
        """A bare issues/ directory without markers is not treated as data."""
        (tmp_path / "issues").mkdir()  # no active/, no counters.json
        with pytest.raises(IssuesDirNotFoundError):
            find_issues_dir(tmp_path)

    def test_counters_json_alone_qualifies(self, tmp_path):
        """A directory with only counters.json is recognized as issues data."""
        issues = tmp_path / "issues"
        issues.mkdir()
        (issues / "counters.json").write_text("{}")
        assert find_issues_dir(tmp_path) == issues


class TestLooksLikeIssuesDir:
    def test_rejects_file(self, tmp_path):
        """A file named issues is not a data directory."""
        f = tmp_path / "issues"
        f.write_text("not a dir")
        assert looks_like_issues_dir(f) is False
