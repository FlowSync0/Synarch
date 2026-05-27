# Local Development

## Backend

Unix-like shell:

```sh
python3 -m venv .venv
source .venv/bin/activate
make install-backend
make verify
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
make PYTHON=.venv\Scripts\python.exe install-backend
make PYTHON=.venv\Scripts\python.exe verify
```

Run the backend stack with Docker:

```sh
cp .env.example .env
make dev-backend
```

`docker compose up --build ...` runs the `state-migrations` one-shot service before `state-service`.
That service applies ordered SQL migrations and then seeds default divisions, agents, and the local
runtime model/cost baseline. The commands are idempotent, so they can run repeatedly against the
same local database.

Core service ports:

- Gateway: `http://localhost:8000`
- Control Plane: `http://localhost:8010`
- State Service: `http://localhost:8020`
- Memory Service: `http://localhost:8030`
- Event Service: `http://localhost:8040`
- Agent Runtime: `http://localhost:8050`
- Model Gateway: `http://localhost:8060`

## State Database

The state-service uses in-memory repositories when `DATABASE_URL` is not set. Set `DATABASE_URL` to
use PostgreSQL through Psycopg 3.

Run migrations against a local PostgreSQL database:

```sh
make migrate-state DATABASE_URL=postgresql+psycopg://synarch:synarch@localhost:5432/synarch
```

Windows PowerShell:

```powershell
make PYTHON=.venv\Scripts\python.exe migrate-state DATABASE_URL="postgresql+psycopg://synarch:synarch@localhost:5432/synarch"
```

Seed default divisions, agents, and the local runtime model/cost baseline:

```sh
make seed-state DATABASE_URL=postgresql+psycopg://synarch:synarch@localhost:5432/synarch
```

Windows PowerShell:

```powershell
make PYTHON=.venv\Scripts\python.exe seed-state DATABASE_URL="postgresql+psycopg://synarch:synarch@localhost:5432/synarch"
```

Run the opt-in PostgreSQL persistence test:

```sh
SYNARCH_POSTGRES_TEST_URL=postgresql+psycopg://synarch:synarch@localhost:5432/synarch make test-integration
```

Windows PowerShell:

```powershell
$env:SYNARCH_POSTGRES_TEST_URL = "postgresql+psycopg://synarch:synarch@localhost:5432/synarch"
make PYTHON=.venv\Scripts\python.exe test-integration
Remove-Item Env:\SYNARCH_POSTGRES_TEST_URL
```

## Frontend

```sh
cd packages/frontend
npm install
npm run lint
npm run typecheck
npm run build
npm run dev
```

The dashboard starts on `http://localhost:3000`.

The frontend proxies backend calls through same-origin Next.js API routes. It uses
`http://127.0.0.1:8010` for control-plane and `http://127.0.0.1:8020` for state-service by default.
Override them when needed:

```powershell
$env:CONTROL_PLANE_URL = "http://127.0.0.1:8010"
$env:STATE_SERVICE_URL = "http://127.0.0.1:8020"
npm run dev
```

The production-oriented operator surface is available at `http://127.0.0.1:3000/app`. The existing
root dashboard remains useful for detailed development traces.

## Operational Readiness

The Gateway exposes a non-mutating readiness report:

```sh
curl http://localhost:8000/readiness
```

The dashboard reads the same report through `GET /api/gateway/readiness`. Each item is
`ready`, `warning`, or `blocked` and includes the manual action to perform when configuration or
human review is required.

The dashboard action center reads `GET /api/gateway/operator-actions`, backed by Gateway
`/operator-actions`. It aggregates open task reviews, credential requests, human assistance
requests, and blocked connector jobs into one project-focused queue.

Connector setup now goes through Gateway `POST /connectors/{service_id}/connections`. API keys are
written once into the local SecretVault directory and state-service only receives `secret_ref` plus a
fingerprint. The default local vault path is `.synarch/secrets`; override it with `SECRET_VAULT_DIR`.
The path is git-ignored. Docker mounts this path through the `synarch_secrets` volume so connector
keys survive container recreation. Set `SECRET_VAULT_KEY` before storing production credentials so
new local vault entries are encrypted at rest; without it, Gateway reports a SecretVault readiness
warning and stores local development secrets as chmod `0600` JSON. Production deployments can still
replace the local file vault with Vault/KMS or the platform secret manager behind the same
`secret_ref` contract. If `SECRET_VAULT_KEY` is added after plaintext local entries already exist,
run Gateway `POST /secret-vault/reencrypt` or the `/app` SecretVault action to rewrite those entries
without exposing the secret values.
OAuth/manual-link connectors can publish `oauth_authorization_url`, `connect_url`, or
`manual_connection_url` in service metadata. Gateway generates a `setup_url` with `state` and
`redirect_uri`, receives `/connectors/{service_id}/oauth/callback`, stores the received code in
SecretVault, and completes the connector connection in state-service without persisting the raw code
in state records.

Manual configuration that commonly matters before unattended use:

- `OPENROUTER_API_KEY` plus `AGENT_RUNTIME_MODE=model_gateway`,
  `MODEL_GATEWAY_MODE=openrouter`, `TASK_RUNNER_PROVIDER_ID=provider-openrouter`, and
  `TASK_RUNNER_MODEL_ID=deepseek/deepseek-v4-flash` for real AI execution.
- `docker compose --profile worker up -d` when scheduler, connector, memory compaction, and
  embedding workers must run continuously. Use `docker compose --profile worker up -d
  work-queue-worker` when a generic durable queue also needs to be consumed.
- `FIRECRAWL_API_KEY` or `BROWSERLESS_API_KEY`, or an active Synarch connector connection backed by
  SecretVault, only when local web extraction is not enough for
  JavaScript, anti-bot, or CAPTCHA-heavy pages.
- Dashboard review queues for credential grants, human assistance, blocked connector jobs, and
  tasks in review.
