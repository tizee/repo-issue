"""BDD tests for collision-safe ID allocation.

Behavior: tickets imported from other repos keep their original IDs, so
issue files may exist with numbers ahead of the counter. New ID allocation
must skip any number already taken by a file in active/ or resolved/.
(FEAT-404)
"""

from __future__ import annotations

import json

from issue_tracker.create_issue import get_next_id
from issue_tracker.init import init_issues_dir


def _write_counter(issues_dir, prefix, value):
    counters_path = issues_dir / "counters.json"
    counters = json.loads(counters_path.read_text())
    counters[prefix] = value
    counters_path.write_text(json.dumps(counters))


def _touch_issue(issues_dir, subdir, issue_id):
    (issues_dir / subdir / f"{issue_id}.md").write_text(f"---\nid: {issue_id}\n---\n")


class TestIdCollisionSkip:
    def test_sequential_allocation_without_imports(self, tmp_path):
        """Normal case: counter drives sequential IDs."""
        issues = init_issues_dir(tmp_path)
        assert get_next_id(issues, "BUG") == "BUG-001"
        assert get_next_id(issues, "BUG") == "BUG-002"

    def test_skips_id_taken_by_imported_active_ticket(self, tmp_path):
        """Counter at N, imported ticket holds N+1: allocation skips it."""
        issues = init_issues_dir(tmp_path)
        _write_counter(issues, "FEAT", 118)
        _touch_issue(issues, "active", "FEAT-119")

        assert get_next_id(issues, "FEAT") == "FEAT-120"

    def test_skips_id_taken_by_resolved_ticket(self, tmp_path):
        """Resolved tickets also reserve their IDs."""
        issues = init_issues_dir(tmp_path)
        _write_counter(issues, "BUG", 9)
        _touch_issue(issues, "resolved", "BUG-010")

        assert get_next_id(issues, "BUG") == "BUG-011"

    def test_skips_consecutive_taken_ids(self, tmp_path):
        """A run of imported IDs is skipped entirely."""
        issues = init_issues_dir(tmp_path)
        _touch_issue(issues, "active", "UI-001")
        _touch_issue(issues, "active", "UI-002")
        _touch_issue(issues, "resolved", "UI-003")

        assert get_next_id(issues, "UI") == "UI-004"

    def test_counter_advances_past_skipped_ids(self, tmp_path):
        """After skipping, the counter records the allocated number."""
        issues = init_issues_dir(tmp_path)
        _touch_issue(issues, "active", "BUG-001")
        _touch_issue(issues, "active", "BUG-002")

        assert get_next_id(issues, "BUG") == "BUG-003"

        counters = json.loads((issues / "counters.json").read_text())
        assert counters["BUG"] == 3
