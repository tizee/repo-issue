"""Tests for YAML frontmatter utilities."""

from __future__ import annotations

import pytest

from issue_tracker.yaml_utils import (
    dump_yaml_frontmatter,
    parse_yaml_frontmatter,
    set_frontmatter_field,
)


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


class TestSetFrontmatterField:
    """Tests for targeted frontmatter line edits on raw file content."""

    CONTENT = """---
id: BUG-001
title: "Fix crash"
status: open
custom_field: something the naive parser may not understand
---

## Summary
Body text.
"""

    def test_replaces_existing_field(self):
        """Setting an existing key rewrites only that line."""
        result = set_frontmatter_field(self.CONTENT, "status", "resolved")

        assert "status: resolved" in result
        assert "status: open" not in result

    def test_adds_missing_field(self):
        """Setting a new key appends it inside the frontmatter block."""
        result = set_frontmatter_field(self.CONTENT, "resolved_date", "2026-07-03")

        parsed = parse_yaml_frontmatter(result)
        assert parsed["resolved_date"] == "2026-07-03"
        # Field must live inside the frontmatter, not the body
        fm_end = result.index("\n---", 3)
        assert result.index("resolved_date") < fm_end

    def test_removes_field_with_none(self):
        """Setting a key to None removes its line."""
        with_date = set_frontmatter_field(self.CONTENT, "resolved_date", "2026-07-03")
        result = set_frontmatter_field(with_date, "resolved_date", None)

        assert "resolved_date" not in result

    def test_preserves_unknown_fields_and_body(self):
        """Fields the parser does not model and the body survive untouched."""
        result = set_frontmatter_field(self.CONTENT, "status", "in_progress")

        assert "custom_field: something the naive parser may not understand" in result
        assert "## Summary\nBody text." in result

    def test_quotes_values_that_need_quoting(self):
        """Values with special characters are written as valid quoted YAML."""
        result = set_frontmatter_field(self.CONTENT, "title", 'He said "hi"')

        parsed = parse_yaml_frontmatter(result)
        assert parsed["title"] == 'He said "hi"'

    def test_no_frontmatter_raises(self):
        """Content without frontmatter cannot be edited."""
        with pytest.raises(ValueError):
            set_frontmatter_field("just a body", "status", "open")


class TestQuoteEscapeRoundTrip:
    """Quotes in values must survive any number of parse/dump cycles.

    Regression: title escaping used to gain one backslash layer per
    round-trip ('\"' -> '\\\"' -> ...), corrupting files on every update.
    """

    def test_parse_unescapes_double_quoted_value(self):
        content = '---\ntitle: "He said \\"hi\\""\n---\n\nBody\n'
        result = parse_yaml_frontmatter(content)

        assert result["title"] == 'He said "hi"'

    def test_dump_parse_round_trip_is_identity(self):
        data = {"title": 'Title with "quotes" and \\ backslash'}

        once = parse_yaml_frontmatter(dump_yaml_frontmatter(data) + "\nBody")
        assert once["title"] == data["title"]

    def test_repeated_round_trips_are_stable(self):
        """N cycles of parse->dump must not change the serialized form."""
        content = dump_yaml_frontmatter({"title": 'With "quotes"'}) + "\nBody"

        for _ in range(3):
            parsed = parse_yaml_frontmatter(content)
            content = dump_yaml_frontmatter(parsed) + "\nBody"
            assert parsed["title"] == 'With "quotes"'


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
