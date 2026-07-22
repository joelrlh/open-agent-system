.PHONY: install format lint test profile verify

install:
	uv sync --all-groups

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .

test:
	uv run pytest --cov=open_agent_system

profile:
	uv run open-agent-system verify --json

verify: lint test profile
