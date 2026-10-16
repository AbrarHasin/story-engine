# Story Engine — Project Instructions

## What This Is
Multi-agent AI story generation platform. Topic → LangGraph pipeline → SSE-streamed story.

## Architecture
```
Frontend (React+Vite :5173)
  → Backend (FastAPI :8080)
    → LangGraph StateGraph
      → START picks sections from include_* flags (plain Python, no LLM call)
        → [Research, LightSide, DarkSide, Facts] (Haiku, parallel)
        → Writer (Haiku 5.5)
        → Synthesizer / critic editor (Haiku 5.5)
      ← SSE stream back to client
  → Langfuse (self-hosted :3000) — full trace per story
```

## Running Services
```bash
curl -s http://localhost:8080/health   # backend health
curl -s http://localhost:5173          # frontend
curl -s http://localhost:3000          # langfuse
```

## Common Tasks

### Start backend (if not running)
```bash
cd /home/abrar/code/story-engine/backend
setsid .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload > /tmp/backend.log 2>&1 &
```

### Start frontend (if not running)
```bash
cd /home/abrar/code/story-engine/frontend
setsid npm run dev -- --host > /tmp/frontend.log 2>&1 &
```

### Run database migration
```bash
cd /home/abrar/code/story-engine/backend
.venv/bin/python -m alembic upgrade head
```

### Run all Playwright tests
```bash
cd /home/abrar/code/story-engine
./node_modules/.bin/playwright test --reporter=list
```

### Run specific test suites
```bash
./node_modules/.bin/playwright test e2e/api.spec.ts       # API + health + SSE
./node_modules/.bin/playwright test e2e/frontend.spec.ts  # Browser UI automation
./node_modules/.bin/playwright test e2e/langfuse.spec.ts  # Observability checks
```

### Check Langfuse traces
Open: http://localhost:3000/project/story-engine/traces
Login: `LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD` in backend/.env (Docker stack; created on Langfuse's first boot)

### Quick story generation test
```bash
cd /home/abrar/code/story-engine/backend
.venv/bin/python test_generate.py
```

## Key Files
| File | Purpose |
|---|---|
| `backend/app/agents/graph.py` | LangGraph topology (8 nodes) |
| `backend/app/agents/nodes.py` | All agent logic + token accounting |
| `backend/app/api/v1/stories.py` | SSE endpoint + DB persistence |
| `backend/app/core/auth.py` | JWT auth + dev fallback |
| `backend/app/core/observability.py` | Langfuse callback handler |
| `frontend/src/hooks/useGenerate.ts` | SSE consumer (fetch-based) |
| `frontend/src/stores/generationStore.ts` | Zustand state |
| `e2e/api.spec.ts` | API-level tests |
| `e2e/frontend.spec.ts` | Browser E2E tests |
| `e2e/langfuse.spec.ts` | Trace verification |

## Environment Variables (backend/.env)
```
ANTHROPIC_API_KEY=...            # ← needed for generation
LANGFUSE_PUBLIC_KEY=pk-lf-...       # generated; Langfuse creates this key on first boot
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000 # the Docker stack overrides it with http://langfuse:3000
LANGFUSE_INIT_USER_EMAIL=...        # Langfuse UI login
LANGFUSE_INIT_USER_PASSWORD=...
DATABASE_URL=postgresql+asyncpg://storyengine:changeme@localhost:5432/storyengine
REDIS_URL=redis://localhost:6379
```

## Model Tiers (token cost discipline)
- Haiku 5.5 (`claude-haiku-5-5`, thinking disabled) → research, light, dark, facts, writer, synthesizer (critic editor)
- Modelled cost per story: ~$0.0009 typical, ~$0.0023 at token caps (not yet measured; prompt caching is a no-op, prefixes are under 512 tokens)

## Dev Constraints
- `backend/.env` is gitignored — never commit it
- `password_hash` column added in migration 0002
- Dev user ID: 00000000-0000-0000-0000-000000000001 (seeded via seed_dev_user.py)
- Auth fallback: no JWT token + default JWT_SECRET_KEY → auto-uses dev user
- Docker builds work now (`.dockerignore` excludes .venv/node_modules)
