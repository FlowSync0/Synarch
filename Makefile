.PHONY: install-backend test lint dev-infra dev-backend

PYTHON ?= python3

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

lint:
	$(PYTHON) -m ruff check .

dev-infra:
	docker compose up postgres redis nats otel-collector prometheus grafana

dev-backend:
	docker compose up --build gateway control-plane state-service memory-service event-service agent-runtime
