"""YAML frontmatter parsing and dumping utilities.

Simple YAML frontmatter handling without external dependencies.
"""

from __future__ import annotations

import re
from typing import Any

# Regex to match YAML frontmatter between --- markers
_FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n?",
    re.DOTALL,
)


def _unescape_double_quoted(value: str) -> str:
    """Reverse the escaping applied when dumping double-quoted values."""
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _escape_double_quoted(value: str) -> str:
    """Escape a value for inclusion inside YAML double quotes.

    Must stay symmetric with _unescape_double_quoted so that any number of
    parse/dump cycles is the identity.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _parse_yaml_block(yaml_text: str) -> dict[str, Any]:
    """Parse a block of simple YAML into a dict.

    Supports: key-value pairs, inline lists, multi-line lists,
    quoted/unquoted strings.
    """
    result: dict[str, Any] = {}

    current_key: str | None = None
    current_list: list[str] = []
    in_list = False

    for line in yaml_text.strip().split("\n"):
        line = line.rstrip()

        if not line:
            continue

        # List item
        if line.strip().startswith("- "):
            if in_list and current_key:
                item = line.strip()[2:].strip().strip('"').strip("'")
                current_list.append(item)
            continue

        # Save list if we were in one
        if in_list and current_key:
            result[current_key] = current_list
            in_list = False
            current_list = []

        # Key-value pair
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_key = key

            if value == "":
                # List start
                in_list = True
                current_list = []
            elif value.startswith("[") and value.endswith("]"):
                # Inline list
                items = value[1:-1].split(",")
                result[key] = [
                    item.strip().strip('"').strip("'") for item in items if item.strip()
                ]
            elif value.startswith('"') and value.endswith('"'):
                result[key] = _unescape_double_quoted(value[1:-1])
            elif value.startswith("'") and value.endswith("'"):
                result[key] = value[1:-1]
            else:
                result[key] = value

    # Handle list at end
    if in_list and current_key:
        result[current_key] = current_list

    return result


def parse_yaml_frontmatter(content: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter from markdown content.

    Returns dict of frontmatter fields, or None if no frontmatter found.
    """
    if not content.startswith("---"):
        return None

    end_match = re.search(r"\n---\s*\n", content)
    if not end_match:
        return None

    yaml_text = content[3 : end_match.start()]
    return _parse_yaml_block(yaml_text)


def split_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """Split markdown content into frontmatter dict and body text.

    Returns (frontmatter_dict, body_content).
    Returns (None, original_content) if no frontmatter found.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        return None, content

    yaml_text = match.group(1)
    body = content[match.end() :]

    return _parse_yaml_block(yaml_text), body


def split_frontmatter_raw(content: str) -> tuple[str | None, str]:
    """Split content into the raw frontmatter block (including --- markers)
    and the body text, without parsing.

    Returns (None, original_content) if no frontmatter found.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        return None, content
    return match.group(0), content[match.end() :]


def _needs_quoting(value: str) -> bool:
    """Check if a string value needs to be quoted in YAML."""
    # Quote if contains special characters, starts/ends with spaces, or is empty
    if not value:
        return True
    if value != value.strip():
        return True
    # Check for characters that need quoting
    special_chars = set('":[]{}#&*!|>\'"%@`')
    if any(c in value for c in special_chars):
        return True
    # Check for values that look like other types
    if value.lower() in ("true", "false", "null", "yes", "no"):
        return True
    return bool(re.match(r"^\d+$", value))


def _format_scalar(value: str) -> str:
    """Format a string value as a YAML scalar, quoting when needed."""
    if _needs_quoting(value):
        return f'"{_escape_double_quoted(value)}"'
    return value


def dump_yaml_frontmatter(data: dict[str, Any]) -> str:
    """Dump frontmatter dictionary to YAML format.

    Simple YAML serialization for frontmatter data.
    Handles strings and lists.
    """
    lines = ["---"]

    for key, value in data.items():
        if isinstance(value, list):
            # Format list inline
            items = [f'"{_escape_double_quoted(str(item))}"' for item in value]
            lines.append(f"{key}: [{', '.join(items)}]")
        elif isinstance(value, str):
            lines.append(f"{key}: {_format_scalar(value)}")
        else:
            # Other values as-is
            lines.append(f"{key}: {value}")

    lines.append("---")
    lines.append("")  # Trailing newline

    return "\n".join(lines)


def set_frontmatter_field(content: str, key: str, value: str | None) -> str:
    """Set, replace, or remove a single frontmatter field via line edit.

    Unlike a parse/dump round-trip, this touches only the target line, so
    fields the simple parser cannot model (comments, exotic values) survive
    byte-for-byte.

    Args:
        content: Full file content starting with a frontmatter block.
        key: Frontmatter key to set.
        value: New value; None removes the field.

    Raises:
        ValueError: If content has no frontmatter block.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        raise ValueError("content has no YAML frontmatter block")

    fm_text = match.group(1)
    body = content[match.end() :]

    lines = fm_text.split("\n") if fm_text else []
    key_prefix = f"{key}:"
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(key_prefix):
            if value is not None and not replaced:
                new_lines.append(f"{key}: {_format_scalar(value)}")
            replaced = True
            continue
        new_lines.append(line)

    if not replaced and value is not None:
        new_lines.append(f"{key}: {_format_scalar(value)}")

    fm_block = "---\n" + "\n".join(new_lines) + ("\n" if new_lines else "") + "---\n"
    return fm_block + body
