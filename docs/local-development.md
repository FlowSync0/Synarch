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
That service applies ordered SQL migrations and then seeds default divisions and agents. The commands
are idempotent, so they can run repeatedly against the same local database.

Core service ports:

- Gateway: `http://localhost:8000`
- Control Plane: `http://localhost:8010`
- State Service: `http://localhost:8020`
- Memory Service: `http://localhost:8030`
- Event Service: `http://localhost:8040`
- Agent Runtime: `http://localhost:8050`

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

Seed default divisions and agents:

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

The frontend proxies control-plane calls through same-origin Next.js API routes. It uses
`http://127.0.0.1:8010` by default. Override it when needed:

```powershell
$env:CONTROL_PLANE_URL = "http://127.0.0.1:8010"
npm run dev
```
