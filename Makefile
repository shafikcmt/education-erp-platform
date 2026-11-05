# Education ERP — developer commands. Run `make help`.
SHELL := /bin/bash
COMPOSE := docker compose
BACKEND := cd backend &&
.DEFAULT_GOAL := help

.PHONY: help env up down logs ps migrate smoke shell \
        install test test-backend test-frontend e2e lint lint-backend lint-frontend \
        typecheck format schema check

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

env: ## Create .env from .env.example (dummy dev values) if missing
	@test -f .env || (cp .env.example .env && echo "created .env")

up: env ## Build and start the full dev stack, wait until healthy
	$(COMPOSE) up -d --build --wait

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

logs: ## Follow logs of all services
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps -a

migrate: ## Run migrations (as the owner role)
	$(COMPOSE) run --rm migrate

smoke: ## End-to-end infrastructure check inside the running stack
	$(COMPOSE) exec -T api python manage.py smoke_check

shell: ## Django shell in the api container
	$(COMPOSE) exec api python manage.py shell

install: ## Install backend (uv) and frontend (pnpm) dependencies locally
	$(BACKEND) uv sync --frozen
	pnpm install --frozen-lockfile

test: test-backend test-frontend ## Run all unit/integration tests

test-backend: ## pytest (needs postgres from `make up`), with coverage gate
	$(BACKEND) uv run pytest --cov --cov-fail-under=85

test-frontend: ## Vitest
	pnpm -r test

e2e: ## Playwright against the running stack (http://localhost:8080)
	pnpm --filter @erp/frontend e2e

lint: lint-backend lint-frontend ## All linters and format checks

lint-backend:
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run lint-imports

lint-frontend:
	pnpm -r lint && pnpm format:check

typecheck: ## mypy + tsc
	$(BACKEND) uv run mypy .
	pnpm -r typecheck

format: ## Auto-format backend and frontend
	$(BACKEND) uv run ruff check --fix . && uv run ruff format .
	pnpm format

schema: ## Regenerate OpenAPI schema + TypeScript client (commit the result)
	$(BACKEND) uv run python manage.py spectacular --settings=config.settings.test \
	  --validate --fail-on-warn --file ../packages/api-client/openapi.yaml
	pnpm api:generate

check: lint typecheck test ## Everything CI runs except Docker/E2E
