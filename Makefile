.PHONY: install-backend test test-unit test-integration test-eval lint verify migrate-state dev-infra dev-backend

PYTHON ?= python3
DATABASE_URL ?= postgresql+psycopg://synarch:synarch@localhost:5432/synarch

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

lint:
	$(PYTHON) -m ruff check .

verify: lint test

migrate-state:
	$(PYTHON) -m synarch_state_service.migrations --database-url "$(DATABASE_URL)"

dev-infra:
	docker compose up postgres redis nats otel-collector prometheus grafana

dev-backend:
	docker compose up --build gateway control-plane state-service memory-service event-service agent-runtime
