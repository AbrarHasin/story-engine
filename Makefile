# Story Engine — Developer Makefile
# Usage: make <target>
# All Python commands run inside backend/.venv

PYTHON      := python3
VENV        := backend/.venv
PIP         := $(VENV)/bin/pip
UVICORN     := $(VENV)/bin/uvicorn
ALEMBIC     := $(VENV)/bin/alembic
PYTEST      := $(VENV)/bin/pytest
RUFF        := $(VENV)/bin/ruff
MYPY        := $(VENV)/bin/mypy

.DEFAULT_GOAL := help

# ── Bootstrap ────────────────────────────────────────────────────────────────

.PHONY: venv
venv: ## Create backend virtual environment
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	@echo "✓ venv ready → activate with: source backend/.venv/bin/activate"

.PHONY: install
install: venv ## Alias for venv

.PHONY: install-dev
install-dev: venv ## Install dev/test extras
	$(PIP) install -r backend/requirements-dev.txt

# ── Dev Servers ──────────────────────────────────────────────────────────────

.PHONY: dev
dev: ## Start full local stack (postgres, redis, langfuse)
	docker compose up -d postgres redis langfuse
	@echo "Waiting for postgres..." && sleep 3
	$(MAKE) migrate
	$(VENV)/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend

.PHONY: up
up: ## Start all services via docker compose
	docker compose up -d

.PHONY: up-infra
up-infra: ## Start only infra (postgres, redis, langfuse) — no app containers
	docker compose up -d postgres redis langfuse

.PHONY: down
down: ## Stop all containers
	docker compose down

.PHONY: logs
logs: ## Tail all container logs
	docker compose logs -f

.PHONY: logs-backend
logs-backend: ## Tail backend logs only
	docker compose logs -f backend

# ── Deploy ───────────────────────────────────────────────────────────────────

.PHONY: deploy
deploy: ## Pull latest, sync deps, migrate, restart services, smoke test
	@echo "[deploy] Pulling latest code..."
	git pull origin master
	@echo "[deploy] Syncing Python dependencies..."
	$(PIP) install -q --upgrade -r backend/requirements.txt
	@echo "[deploy] Running database migrations..."
	cd backend && .venv/bin/alembic upgrade head
	@echo "[deploy] Restarting backend..."
	bash scripts/restart-backend.sh
	@echo "[deploy] Restarting frontend..."
	bash scripts/restart-frontend.sh
	@echo "[deploy] Waiting for backend to come up..."
	sleep 6
	@echo "[deploy] Smoke test..."
	@curl -sf http://localhost:8080/health | python3 -c "\
import sys, json; \
d = json.load(sys.stdin); \
print('[deploy] Health:', d); \
sys.exit(0 if d.get('status') in ('ok', 'degraded') else 1)"
	@echo "[deploy] Done."

# ── Database ─────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## Run Alembic migrations (upgrade head)
	cd backend && .venv/bin/alembic upgrade head

.PHONY: migration
migration: ## Create a new migration (NAME=<description>)
	cd backend && .venv/bin/alembic revision --autogenerate -m "$(NAME)"

.PHONY: db-reset
db-reset: ## Drop + recreate DB and run migrations fresh
	docker compose exec postgres psql -U storyengine -c "DROP DATABASE IF EXISTS storyengine;"
	docker compose exec postgres psql -U storyengine -c "CREATE DATABASE storyengine;"
	$(MAKE) migrate

# ── Testing ──────────────────────────────────────────────────────────────────

.PHONY: test
test: ## Run all tests
	cd backend && ../$(PYTEST) tests/ -v --tb=short

.PHONY: test-agents
test-agents: ## Run only agent/graph tests
	cd backend && ../$(PYTEST) tests/test_agents.py -v

.PHONY: test-api
test-api: ## Run only API endpoint tests
	cd backend && ../$(PYTEST) tests/test_api.py -v

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	cd backend && ../$(PYTEST) tests/ --cov=app --cov-report=term-missing

# ── Lint / Format ────────────────────────────────────────────────────────────

.PHONY: lint
lint: ## Lint with ruff
	$(RUFF) check backend/app backend/tests

.PHONY: format
format: ## Format with ruff
	$(RUFF) format backend/app backend/tests

.PHONY: typecheck
typecheck: ## Type-check with mypy
	$(MYPY) backend/app --ignore-missing-imports

.PHONY: check
check: lint typecheck ## Run all checks

# ── Playwright E2E ───────────────────────────────────────────────────────────

.PHONY: e2e-install
e2e-install: ## Install Playwright browsers
	npx playwright install --with-deps chromium

.PHONY: e2e
e2e: ## Run Playwright E2E tests
	npx playwright test

.PHONY: e2e-ui
e2e-ui: ## Open Playwright test UI
	npx playwright test --ui

# ── Observability ─────────────────────────────────────────────────────────────

.PHONY: langfuse
langfuse: ## Open Langfuse dashboard in browser
	open http://localhost:3000 || start http://localhost:3000

.PHONY: docs
docs: ## Open FastAPI Swagger UI
	open http://localhost:8000/docs || start http://localhost:8000/docs

# ── Utilities ────────────────────────────────────────────────────────────────

.PHONY: shell
shell: ## Open Python shell with app context loaded
	cd backend && ../$(VENV)/bin/ipython -i -c "from app.core.config import settings; print(settings)"

.PHONY: clean
clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	@echo "✓ cleaned"

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
