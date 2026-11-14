.DEFAULT_GOAL := help

PYTHON ?= python3
RUFF ?= ruff
COMPOSE ?= docker compose
BUILD_OPTIONS ?=
PYTHON_PATHS ?= src/infer tests docker
RUFF_EXCLUDE := vendor

.PHONY: help format format-check lint test check compose-check image image-push

help: ## Show available targets.
	@awk 'BEGIN {FS = ":.*##"} /^[a-z][a-z0-9-]*:.*##/ {printf "%-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

format: ## Format adapter, tests, and Docker helper Python files with Ruff.
	@$(RUFF) format --isolated --force-exclude --exclude '$(RUFF_EXCLUDE)' $(PYTHON_PATHS)

format-check: ## Check Python formatting without changing files.
	@$(RUFF) format --isolated --check --force-exclude --exclude '$(RUFF_EXCLUDE)' $(PYTHON_PATHS)

lint: ## Check Python syntax and common errors with Ruff.
	@$(RUFF) check --isolated --select E4,E7,E9,F --force-exclude --exclude '$(RUFF_EXCLUDE)' $(PYTHON_PATHS)

test: ## Run the CPU-only adapter unit tests.
	@$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

check: lint format-check test ## Run lint, format checks, and CPU-only tests.

compose-check: ## Validate the Docker Compose configuration.
	@$(COMPOSE) config --quiet

image: ## Build the Flora image defined in docker-compose.yml.
	@$(COMPOSE) build $(BUILD_OPTIONS) flora

image-push: ## Push the configured Flora image to its registry.
	@$(COMPOSE) push flora
