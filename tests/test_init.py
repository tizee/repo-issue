"""BDD tests for 'issue init' scaffolding.

Behavior: init creates the full issues/ layout (active/, resolved/,
templates/ with bundled defaults, counters.json) and is idempotent --
existing files are never overwritten.
"""

from __future__ import annotations

import json

from issue_tracker.init import DEFAULT_COUNTERS, init_issues_dir


class TestInitIssuesDir:
    def test_creates_full_layout(self, tmp_path):
        """Fresh init creates all directories, templates, and counters."""
        issues = init_issues_dir(tmp_path)

        assert issues == tmp_path / "issues"
        assert (issues / "active").is_dir()
        assert (issues / "resolved").is_dir()
        assert (issues / "templates" / "bug_report.md").is_file()
        assert (issues / "templates" / "feature_request.md").is_file()
        assert (issues / "templates" / "ui_regression.md").is_file()
        assert json.loads((issues / "counters.json").read_text()) == DEFAULT_COUNTERS

    def test_idempotent_preserves_existing_data(self, tmp_path):
        """Re-running init never overwrites counters or customized templates."""
        issues = init_issues_dir(tmp_path)
        (issues / "counters.json").write_text(json.dumps({"BUG": 42}))
        custom = "# my custom template"
        (issues / "templates" / "bug_report.md").write_text(custom)

        init_issues_dir(tmp_path)

        assert json.loads((issues / "counters.json").read_text()) == {"BUG": 42}
        assert (issues / "templates" / "bug_report.md").read_text() == custom

    def test_templates_render_valid_issues(self, tmp_path):
        """Bundled templates work with create_issue end to end."""
        from issue_tracker.create_issue import create_issue

        issues = init_issues_dir(tmp_path)
        path = create_issue("bug_report", "Scaffolded bug", issues_dir=issues)

        content = path.read_text()
        assert "id: BUG-001" in content
        assert "Scaffolded bug" in content
        assert "{{" not in content  # all placeholders substituted
