.PHONY: install-backend test test-unit test-integration test-eval test-live-openrouter test-live-model-gateway-openrouter test-live-connector-jobs-openrouter test-live-lifecycle-openrouter test-live-web-extract-blocked-openrouter test-live-memory-embedding test-live-memory-bridge test-live-memory-graph scheduler-tick scheduler-loop scheduler-worker connector-job-tick connector-job-loop connector-job-worker memory-compaction-tick memory-compaction-loop memory-compaction-worker memory-embedding-backfill-tick memory-embedding-backfill-loop memory-embedding-backfill-worker work-queue-tick work-queue-loop work-queue-worker lint typecheck verify migrate-state seed-state seed-system-memory dev-infra dev-backend

PYTHON ?= python3
DATABASE_URL ?= postgresql+psycopg://synarch:synarch@localhost:5432/synarch
MYPY_CACHE_DIR ?= .mypy_cache
GATEWAY_URL ?= http://localhost:8000
SYNARCH_SCHEDULER_MAX_TASKS ?= 3
SYNARCH_SCHEDULER_INTERVAL_SECONDS ?= 30
SYNARCH_CONNECTOR_JOB_MAX_JOBS ?= 3
SYNARCH_CONNECTOR_JOB_INTERVAL_SECONDS ?= 30
SYNARCH_MEMORY_COMPACTION_SCOPE ?=
SYNARCH_MEMORY_COMPACTION_PROJECT_ID ?=
SYNARCH_MEMORY_COMPACTION_MIN_SOURCE_TOKENS ?= 1200
SYNARCH_MEMORY_COMPACTION_MAX_SCOPES ?= 20
SYNARCH_MEMORY_COMPACTION_INTERVAL_SECONDS ?= 300
SYNARCH_MEMORY_EMBEDDING_PROJECT_ID ?=
SYNARCH_MEMORY_EMBEDDING_AGENT_ID ?=
SYNARCH_MEMORY_EMBEDDING_SCOPE ?=
SYNARCH_MEMORY_EMBEDDING_MAX_ITEMS ?= 10
SYNARCH_MEMORY_EMBEDDING_INTERVAL_SECONDS ?= 300
STATE_SERVICE_URL ?= http://localhost:8020
SYNARCH_WORK_QUEUE_NAME ?= reminders
SYNARCH_WORK_QUEUE_MAX_ITEMS ?= 5
SYNARCH_WORK_QUEUE_LEASE_SECONDS ?= 300
SYNARCH_WORK_QUEUE_INTERVAL_SECONDS ?= 30

install-backend:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e shared/models
	$(PYTHON) -m pip install -e packages/gateway
	$(PYTHON) -m pip install -e packages/control-plane
	$(PYTHON) -m pip install -e packages/state-service
	$(PYTHON) -m pip install -e packages/memory-service
	$(PYTHON) -m pip install -e packages/event-service
	$(PYTHON) -m pip install -e packages/model-gateway
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

test-live-model-gateway-openrouter:
	scripts/live_model_gateway_openrouter_e2e.sh

test-live-connector-jobs-openrouter:
	scripts/live_connector_job_list_stop_openrouter_e2e.sh

test-live-lifecycle-openrouter:
	scripts/live_lifecycle_openrouter_e2e.sh

test-live-web-extract-blocked-openrouter:
	scripts/live_web_extract_blocked_openrouter_e2e.sh

test-live-memory-embedding:
	scripts/live_memory_embedding_backfill_e2e.sh

test-live-memory-bridge:
	scripts/live_memory_bridge_scope_e2e.sh

test-live-memory-graph:
	scripts/live_memory_bridge_scope_e2e.sh

scheduler-tick:
	$(PYTHON) scripts/scheduler_tick.py --gateway-url "$(GATEWAY_URL)" --state-service-url "$(STATE_SERVICE_URL)" --max-tasks "$(SYNARCH_SCHEDULER_MAX_TASKS)"

scheduler-loop:
	$(PYTHON) scripts/scheduler_tick.py --gateway-url "$(GATEWAY_URL)" --state-service-url "$(STATE_SERVICE_URL)" --max-tasks "$(SYNARCH_SCHEDULER_MAX_TASKS)" --loop --interval-seconds "$(SYNARCH_SCHEDULER_INTERVAL_SECONDS)"

scheduler-worker:
	docker compose up --build scheduler-worker

connector-job-tick:
	$(PYTHON) scripts/connector_job_tick.py --gateway-url "$(GATEWAY_URL)" --state-service-url "$(STATE_SERVICE_URL)" --max-jobs "$(SYNARCH_CONNECTOR_JOB_MAX_JOBS)"

connector-job-loop:
	$(PYTHON) scripts/connector_job_tick.py --gateway-url "$(GATEWAY_URL)" --state-service-url "$(STATE_SERVICE_URL)" --max-jobs "$(SYNARCH_CONNECTOR_JOB_MAX_JOBS)" --loop --interval-seconds "$(SYNARCH_CONNECTOR_JOB_INTERVAL_SECONDS)"

connector-job-worker:
	docker compose up --build connector-job-worker

memory-compaction-tick:
	$(PYTHON) scripts/memory_compaction_tick.py --gateway-url "$(GATEWAY_URL)" --state-service-url "$(STATE_SERVICE_URL)" --scope "$(SYNARCH_MEMORY_COMPACTION_SCOPE)" --project-id "$(SYNARCH_MEMORY_COMPACTION_PROJECT_ID)" --min-source-tokens "$(SYNARCH_MEMORY_COMPACTION_MIN_SOURCE_TOKENS)" --max-scopes "$(SYNARCH_MEMORY_COMPACTION_MAX_SCOPES)"

memory-compaction-loop:
	$(PYTHON) scripts/memory_compaction_tick.py --gateway-url "$(GATEWAY_URL)" --state-service-url "$(STATE_SERVICE_URL)" --scope "$(SYNARCH_MEMORY_COMPACTION_SCOPE)" --project-id "$(SYNARCH_MEMORY_COMPACTION_PROJECT_ID)" --min-source-tokens "$(SYNARCH_MEMORY_COMPACTION_MIN_SOURCE_TOKENS)" --max-scopes "$(SYNARCH_MEMORY_COMPACTION_MAX_SCOPES)" --loop --interval-seconds "$(SYNARCH_MEMORY_COMPACTION_INTERVAL_SECONDS)"

memory-compaction-worker:
	docker compose up --build memory-compaction-worker

memory-embedding-backfill-tick:
	$(PYTHON) scripts/memory_embedding_backfill_tick.py --gateway-url "$(GATEWAY_URL)" --state-service-url "$(STATE_SERVICE_URL)" --project-id "$(SYNARCH_MEMORY_EMBEDDING_PROJECT_ID)" --agent-id "$(SYNARCH_MEMORY_EMBEDDING_AGENT_ID)" --scope "$(SYNARCH_MEMORY_EMBEDDING_SCOPE)" --max-items "$(SYNARCH_MEMORY_EMBEDDING_MAX_ITEMS)"

memory-embedding-backfill-loop:
	$(PYTHON) scripts/memory_embedding_backfill_tick.py --gateway-url "$(GATEWAY_URL)" --state-service-url "$(STATE_SERVICE_URL)" --project-id "$(SYNARCH_MEMORY_EMBEDDING_PROJECT_ID)" --agent-id "$(SYNARCH_MEMORY_EMBEDDING_AGENT_ID)" --scope "$(SYNARCH_MEMORY_EMBEDDING_SCOPE)" --max-items "$(SYNARCH_MEMORY_EMBEDDING_MAX_ITEMS)" --loop --interval-seconds "$(SYNARCH_MEMORY_EMBEDDING_INTERVAL_SECONDS)"

memory-embedding-backfill-worker:
	docker compose up --build memory-embedding-worker

work-queue-tick:
	$(PYTHON) -m synarch_state_service.work_queue_worker --state-service-url "$(STATE_SERVICE_URL)" --queue-name "$(SYNARCH_WORK_QUEUE_NAME)" --limit "$(SYNARCH_WORK_QUEUE_MAX_ITEMS)" --lease-seconds "$(SYNARCH_WORK_QUEUE_LEASE_SECONDS)"

work-queue-loop:
	$(PYTHON) -m synarch_state_service.work_queue_worker --state-service-url "$(STATE_SERVICE_URL)" --queue-name "$(SYNARCH_WORK_QUEUE_NAME)" --limit "$(SYNARCH_WORK_QUEUE_MAX_ITEMS)" --lease-seconds "$(SYNARCH_WORK_QUEUE_LEASE_SECONDS)" --loop --interval-seconds "$(SYNARCH_WORK_QUEUE_INTERVAL_SECONDS)"

work-queue-worker:
	docker compose --profile worker up --build work-queue-worker

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy shared/models packages/gateway packages/control-plane packages/state-service packages/memory-service packages/event-service packages/model-gateway packages/agent-runtime --cache-dir "$(MYPY_CACHE_DIR)"

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
	docker compose up --build gateway control-plane state-service memory-service event-service model-gateway agent-runtime
