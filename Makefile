.PHONY: install reinstall uninstall test lint format check

# Install (or upgrade) the globally available `issue` CLI from this source tree.
# `--force` makes it idempotent: rerun after any code change to pick it up.
install:
	uv tool install --force --from . repo-issue

# Explicit alias for upgrading an already-installed copy.
reinstall: install

uninstall:
	uv tool uninstall repo-issue

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

# Format check + lint + tests, as run in CI.
check: lint test
