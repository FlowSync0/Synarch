.PHONY: install-backend test test-unit test-integration test-eval test-live-openrouter scheduler-tick scheduler-loop lint typecheck verify migrate-state seed-state seed-system-memory dev-infra dev-backend

PYTHON ?= python3
DATABASE_URL ?= postgresql+psycopg://synarch:synarch@localhost:5432/synarch
MYPY_CACHE_DIR ?= .mypy_cache
GATEWAY_URL ?= http://localhost:8000
SYNARCH_SCHEDULER_MAX_TASKS ?= 3
SYNARCH_SCHEDULER_INTERVAL_SECONDS ?= 30

install-backend:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e shared/models
	$(PYTHON) -m pip install -e packages/gateway
	$(PYTHON) -m pip install -e packages/control-plane
	$(PYTHON) -m pip install -e packages/state-service
	$(PYTHON) -m pip install -e packages/memory-service
	$(PYTHON) -m pip install -e packages/event-service
	$(PYTHON) -m pip install -e packages/agent-runtime
	$(PYTHON) -m pip install pytest ruff mypy

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest -m "not integration and not eval"

test-integration:
	$(PYTHON) -m pytest -m integration

test-eval:
	$(PYTHON) -m pytest -m eval

test-live-openrouter:
	scripts/live_openrouter_e2e.sh

scheduler-tick:
	$(PYTHON) scripts/scheduler_tick.py --gateway-url "$(GATEWAY_URL)" --max-tasks "$(SYNARCH_SCHEDULER_MAX_TASKS)"

scheduler-loop:
	$(PYTHON) scripts/scheduler_tick.py --gateway-url "$(GATEWAY_URL)" --max-tasks "$(SYNARCH_SCHEDULER_MAX_TASKS)" --loop --interval-seconds "$(SYNARCH_SCHEDULER_INTERVAL_SECONDS)"

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy shared/models packages/gateway packages/control-plane packages/state-service packages/memory-service packages/event-service packages/agent-runtime --cache-dir "$(MYPY_CACHE_DIR)"

verify: lint typecheck test

migrate-state:
	$(PYTHON) -m synarch_state_service.migrations --database-url "$(DATABASE_URL)"

seed-state:
	$(PYTHON) -m synarch_state_service.seeds --database-url "$(DATABASE_URL)"

seed-system-memory:
	$(PYTHON) scripts/seed_system_memory.py

dev-infra:
	docker compose up postgres redis nats otel-collector prometheus grafana

dev-backend:
	docker compose up --build gateway control-plane state-service memory-service event-service agent-runtime
