.PHONY: install format lint test profile worker ask verify-python verify

install:
	uv sync --all-groups
	npm ci

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

worker:
	npm run worker:check

ask: export OPEN_AGENT_QUERY := $(value QUERY)
ask: export OPEN_AGENT_SANDBOX := $(value SANDBOX)
ask: export OPEN_AGENT_ATTEMPTS := $(value ATTEMPTS)
ask:
	@./integrations/nemoclaw/ask.sh

verify-python: lint test profile

verify: verify-python worker
