.PHONY: format lint format-check

# Apply black formatting + ruff auto-fixes (import sorting, upgrades, etc.)
format:
	ruff check --fix .
	black .

# Fail (without modifying files) if anything is unformatted or lint-broken.
# This is what CI should run.
lint:
	ruff check .
	black --check .

format-check: lint
