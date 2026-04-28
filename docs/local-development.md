# Local Development

## Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
make install-backend
make test
```

Run the backend stack with Docker:

```bash
cp .env.example .env
make dev-backend
```

Core service ports:

- Gateway: `http://localhost:8000`
- Control Plane: `http://localhost:8010`
- State Service: `http://localhost:8020`
- Memory Service: `http://localhost:8030`
- Event Service: `http://localhost:8040`
- Agent Runtime: `http://localhost:8050`

## Frontend

```bash
cd packages/frontend
npm install
npm run dev
```

The dashboard starts on `http://localhost:3000`.
