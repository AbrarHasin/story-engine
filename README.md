# Story Engine — Multi-Agent Story Generation Platform

> Served at **storyteller.techvigilant.com** · Built with LangGraph + FastAPI + React

## Overview

A multi-agent AI platform that generates comprehensive stories from a topic, tonality,
audience, and length. Each story includes a light side (pros), dark side (cons),
interesting facts, and a main narrative — written by a tiered model pipeline optimised
for minimal token spend.

## Tech Stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph + LangChain |
| Backend API | FastAPI (Python, async) |
| Model Gateway | LiteLLM proxy |
| Frontend | React + Vite + TypeScript + Tailwind |
| Database | PostgreSQL + pgvector |
| Cache / State | Redis |
| Payment | SSLCommerz (Bangladesh) |
| Auth | Auth0 / Cognito |
| Deployment | Docker → Cloudflare Tunnel → storyteller.techvigilant.com |
| Observability | LangSmith |

## Project Structure

```
story-engine/
├── backend/           FastAPI + LangGraph orchestration
│   └── app/
│       ├── agents/    Supervisor, Research, Light, Dark, Facts, Writer, Synthesizer
│       ├── api/       REST + SSE endpoints
│       ├── models/    Pydantic schemas + DB models
│       ├── payment/   SSLCommerz integration
│       └── services/  Redis cache, LangSmith, pgvector RAG
├── frontend/          React + Vite SPA
├── docs/              Architecture docs, ADRs
├── .github/workflows/ CI/CD — lint → test → build → deploy
└── docker-compose.yml Local dev stack
```

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/<your-username>/story-engine.git
cd story-engine

# 2. Copy env files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 3. Start the stack (builds, migrates, waits for /health)
scripts/local-up.sh

# 4. Backend: http://localhost:8080
# 5. Frontend: http://localhost:5173
# 6. Docs: http://localhost:8080/docs
```

### Local stack in Docker

| Command | What it does |
|---|---|
| `scripts/local-up.sh` | Build and start postgres, redis, backend (:8080) and frontend (:5173); the backend runs `alembic upgrade head` on start |
| `scripts/local-down.sh` | Stop and remove the containers; data volumes and images are kept |
| `scripts/local-down.sh --destroy` | Also delete the data volumes (database included) and the images compose built |

- The backend reads `backend/.env` (`LLM_PROVIDER`, `ANTHROPIC_API_KEY`, ...); compose only sets the
  in-network `DATABASE_URL` and `REDIS_URL`.
- Langfuse is optional: `COMPOSE_PROFILES=langfuse scripts/local-up.sh` (dashboard on :3000).
- Local gemma via Docker Model Runner: set `LLM_PROVIDER=local` in `backend/.env`, then
  `docker compose -f docker-compose.yml -f docker-compose.gemma.yml up -d`.
- The old host services (`story-backend`, `story-frontend` systemd user units) are disabled; to go
  back: `scripts/local-down.sh && systemctl --user enable --now story-backend story-frontend`.

## Deployment

Served via Cloudflare Tunnel at `storyteller.techvigilant.com`.
See `docs/cloudflare-tunnel.md` for tunnel config and DNS setup.

## Payments

Integrated with **SSLCommerz** — Bangladesh's largest payment gateway.
Supports: Visa, Mastercard, bKash, Nagad, Rocket, AMEX, Bangla QR, EMI.
Sandbox: https://developer.sslcommerz.com

## Contributing / Feature Workflow

Each feature gets its own branch → PR → merge → auto-deploy.

```bash
git checkout -b feature/langgraph-supervisor
# ... build ...
git add . && git commit -m "feat: add supervisor node with Haiku routing"
git push origin feature/langgraph-supervisor
```
