"""Tests for YAML frontmatter utilities."""

from __future__ import annotations

from issue_tracker.yaml_utils import dump_yaml_frontmatter, parse_yaml_frontmatter


class TestParseYamlFrontmatter:
    """Tests for parse_yaml_frontmatter function."""

    def test_parse_simple_frontmatter(self):
        """Test parsing simple key-value pairs."""
        content = """---
id: BUG-001
title: "Fix crash"
status: open
type: BUG
---

## Summary
Body content here.
"""
        result = parse_yaml_frontmatter(content)

        assert result is not None
        assert result["id"] == "BUG-001"
        assert result["title"] == "Fix crash"
        assert result["status"] == "open"
        assert result["type"] == "BUG"

    def test_parse_inline_list(self):
        """Test parsing inline list syntax."""
        content = """---
id: FEAT-001
labels: ["enhancement", "triage"]
---

Body
"""
        result = parse_yaml_frontmatter(content)

        assert result is not None
        assert result["labels"] == ["enhancement", "triage"]

    def test_parse_block_list(self):
        """Test parsing block list syntax."""
        content = """---
id: BUG-001
labels:
  - bug
  - critical
---

Body
"""
        result = parse_yaml_frontmatter(content)

        assert result is not None
        assert result["labels"] == ["bug", "critical"]

    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "## Summary\n\nJust body content."
        result = parse_yaml_frontmatter(content)

        assert result is None

    def test_parse_empty_frontmatter(self):
        """Test parsing empty frontmatter."""
        content = """---
---

Body
"""
        result = parse_yaml_frontmatter(content)

        assert result is not None
        assert result == {}

    def test_parse_single_quotes(self):
        """Test parsing single-quoted strings."""
        content = """---
title: 'Single quoted title'
---

Body
"""
        result = parse_yaml_frontmatter(content)

        assert result is not None
        assert result["title"] == "Single quoted title"

    def test_parse_unquoted_values(self):
        """Test parsing unquoted values."""
        content = """---
status: open
type: BUG
author: agent
---

Body
"""
        result = parse_yaml_frontmatter(content)

        assert result is not None
        assert result["status"] == "open"
        assert result["type"] == "BUG"
        assert result["author"] == "agent"


class TestDumpYamlFrontmatter:
    """Tests for dump_yaml_frontmatter function."""

    def test_dump_simple_frontmatter(self):
        """Test dumping simple key-value pairs."""
        data = {
            "id": "BUG-001",
            "title": "Fix crash",
            "status": "open",
        }
        result = dump_yaml_frontmatter(data)

        # Simple strings don't need quoting
        assert "id: BUG-001" in result
        assert "title: Fix crash" in result
        assert "status: open" in result
        assert result.startswith("---\n")
        assert result.endswith("\n---\n")

    def test_dump_list_field(self):
        """Test dumping frontmatter with list field."""
        data = {
            "id": "FEAT-001",
            "labels": ["enhancement", "triage"],
        }
        result = dump_yaml_frontmatter(data)

        assert 'labels: ["enhancement", "triage"]' in result

    def test_dump_escapes_quotes_in_title(self):
        """Test that quotes in title are escaped."""
        data = {
            "title": 'Title with "quotes"',
        }
        result = dump_yaml_frontmatter(data)

        assert 'title: "Title with \\"quotes\\""' in result

    def test_dump_preserves_order(self):
        """Test that field order is preserved."""
        from collections import OrderedDict

        data = OrderedDict(
            [
                ("id", "BUG-001"),
                ("title", "Fix"),
                ("status", "open"),
            ]
        )
        result = dump_yaml_frontmatter(data)

        lines = [ln for ln in result.split("\n") if ln and not ln.startswith("---")]
        assert lines[0] == "id: BUG-001"
        assert lines[1] == "title: Fix"
        assert lines[2] == "status: open"


class TestRoundTrip:
    """Tests for parse -> dump roundtrip."""

    def test_roundtrip_preserves_data(self):
        """Test that parse then dump preserves all data."""
        original = """---
id: BUG-001
title: "Fix crash"
status: open
type: BUG
labels: ["bug", "critical"]
---

## Summary
Body content
"""
        parsed = parse_yaml_frontmatter(original)
        dumped = dump_yaml_frontmatter(parsed)
        reparsed = parse_yaml_frontmatter(dumped + "\n\n## Summary\nBody content")

        assert reparsed["id"] == "BUG-001"
        assert reparsed["title"] == "Fix crash"
        assert reparsed["status"] == "open"
        assert reparsed["type"] == "BUG"
        assert reparsed["labels"] == ["bug", "critical"]
