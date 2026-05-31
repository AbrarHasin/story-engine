# Project: Multi-Agent Story Engine — Cowork Session Instruction

## Who You Are Working With
- **Name:** Abrar Hasin (DevOps/Cloud Engineer, ~5 years XP)
- **Certs:** AWS Solutions Architect Associate, Terraform Associate
- **Stack fluency:** Docker, containers, ECS/EKS, LiteLLM proxy, LangGraph/LangChain, FastAPI, React
- **Home lab:** ZimaOS (Mac Mini 2014, 4GB RAM) at 192.168.0.127, runs Postgres, Redis, Immich, Home Assistant, Cloudflare Tunnel — all Docker
- **Domain:** techvigilant.com (Cloudflare, zone ID: c1f525bdc6a810b8bdba76c6716f6276)
- **GitHub email:** abrarhasinpranto@gmail.com
- **Project path on AbrarPC (Windows):** E:\Code\Projects\story-engine
- **Project path on ZimaOS (prod):** /DATA/AppData/story-engine
- **Live URL:** https://storyteller.techvigilant.com
- **Style:** Technical and direct. Show code, not pseudocode. Build iteratively, review together.

---

## Project Goal

Build a **multi-agent AI story generation platform** that takes topic, tonality, audience,
and length, then produces a comprehensive story with:
- Light side (pros / bright angles)
- Dark side (cons / risks / shadows)
- Interesting facts
- Main narrative (tone/style driven)

Users can **save and remix Personalities** (named presets: voice, tone, reading level,
banned words). Architecture is primarily optimised around **context token spend**.

---

## What Has Already Been Designed (Do NOT re-explain — build forward)

### Architecture — 5-Layer System
```
Layer 1 — FRONTEND     React + Vite + TypeScript + Tailwind + shadcn/ui
Layer 2 — EDGE         Cloudflare CDN → Cloudflare Tunnel → storyteller.techvigilant.com
Layer 3 — BACKEND API  FastAPI (async) · SSE streaming · Run Manager · Rate Limit/Quota
Layer 4 — ORCHESTRATION LangGraph StateGraph (supervisor pattern) ← THE CORE
Layer 5 — DATA/MODELS  PostgreSQL + pgvector · Redis · LLM Tiers · Prompt Cache · S3/R2
```
Excalidraw diagram checkpoint: `a14d54ee574840d5a5`

### LangGraph Orchestration — Supervisor Pattern
```
Entry → Supervisor/Router (Haiku, cheap)
           ↓ fan-out (parallel)
  ┌─────────┬──────────┬──────────┬──────────┐
Research  LightSide  DarkSide   Facts    [all Haiku]
  └─────────┴──────────┴──────────┴──────────┘
           ↓ fan-in
     Story Writer (Sonnet/Opus — ONLY premium node)
           ↓
     Synthesizer / Editor (Sonnet)
           ↓
     SSE stream → Frontend

Side nodes:
  Personality Injector → feeds voice/style into Story Writer
  Shared State + Checkpointer ↔ Supervisor (Redis or Postgres backend)
```

### Tech Stack (locked in)
| Layer | Choice | Note |
|---|---|---|
| API | FastAPI async | SSE + WebSocket native |
| Orchestration | LangGraph + LangChain | StateGraph, fan-out, checkpointer |
| Model gateway | LiteLLM proxy | Multi-provider fallback, Bedrock-compatible |
| DB | PostgreSQL + pgvector | Users, stories, personalities, RAG |
| Cache/State | Redis | Checkpointer, semantic cache, sessions |
| Object store | S3 / Cloudflare R2 | Exports (PDF, Markdown) |
| Auth | Auth0 / Cognito | JWT, SSO-ready |
| **Payment** | **SSLCommerz** | Bangladesh-primary, replaces Stripe |
| Observability | LangSmith | Per-node token tracing |
| Frontend state | Zustand + TanStack Query | |
| Streaming | SSE (EventSource) | One-way token stream |
| Deploy | Docker → Cloudflare Tunnel | ZimaOS host, auto via GitHub Actions |

### Payment: SSLCommerz (Bangladesh)
- **Provider:** SSLCommerz — largest payment gateway in Bangladesh (est. 2010, 16,770+ merchants)
- **Supported methods:** Visa, Mastercard, bKash, Nagad, Rocket, AMEX, Bangla QR, EMI
- **Pricing:** 2.5% per transaction (3.5% AMEX), one-time setup ৳25,500
- **API docs:** https://sslcommerz.com/integration-document/
- **GitHub SDKs:** https://github.com/sslcommerz
- **Sandbox:** https://developer.sslcommerz.com/registration/
- **IPN:** HTTP IPN Listener for async payment confirmation
- **Key endpoints:** Payment Validation API, Session Query API, Transaction Query API
- **Env vars:** SSLCOMMERZ_STORE_ID, SSLCOMMERZ_STORE_PASS, SSLCOMMERZ_SANDBOX
- **IPN URL in prod:** https://storyteller.techvigilant.com/api/payment/ipn
- International payments also supported (for future global expansion)

### Deployment: storyteller.techvigilant.com via Cloudflare Tunnel
- Cloudflare Zone ID: c1f525bdc6a810b8bdba76c6716f6276
- DNS: CNAME storyteller → <TUNNEL_ID>.cfargotunnel.com (proxied)
- Tunnel config on ZimaOS: /root/.cloudflared/config.yml
- Add ingress rule for storyteller.techvigilant.com → nginx:80 (which proxies / → frontend, /api → backend)
- Wrangler CLI command to add DNS: see docs/cloudflare-tunnel.md

### GitHub Workflow (feature-branch → auto-deploy)
- Repo: https://github.com/abrarhasin/story-engine (create if not yet created)
- Branch strategy: main (prod), develop, feature/* branches
- Each feature: git checkout -b feature/name → commit → push → PR → merge → auto-deploy
- CI/CD: .github/workflows/deploy.yml — lint → test → build Docker images → SSH deploy to ZimaOS
- Required GitHub Secrets: ZIMAOS_HOST (192.168.0.127), ZIMAOS_USER, ZIMAOS_SSH_KEY

### Token Optimisation Strategy (PRIMARY design constraint)
Six levers, in impact order:
1. Model tiering — Haiku for routing/sub-agents, Sonnet for writer/synthesizer, Opus only for premium plan
2. Prompt caching — personality + system prompt cached per session → 90% reduction on cached input
3. Context compression — each node reads only its state fields; summariser before writer
4. Structured outputs — sub-agents emit 3-5 JSON bullets; hard cap on output tokens
5. Semantic cache — Redis + embeddings; repeat (topic, tone, audience) → serve cached result
6. Batch API — 50% off for non-interactive / pre-generation (stacks with caching)

### Cost Model (June 2026 pricing)
| Model | In / Out per MTok | Use in graph |
|---|---|---|
| Haiku 4.5 | $1.00 / $5.00 | Router + 4 sub-agents |
| Sonnet 4.6 | $3.00 / $15.00 | Writer + Synthesizer |
| Opus 4.7 | $5.00 / $25.00 | Premium plan writer only |

Per-story cost (optimised with caching + compression): ~$0.19
Per-story cost (naive, all Opus, no cache): ~$1.03

### UI Screens (decided)
1. Config Panel — topic, tonality, audience, length, perspective toggles
2. Live Generation View — split/tabbed: Story / Light Side / Dark Side / Facts (each streamed independently)
3. Personality Manager — CRUD presets (name, voice, tone, banned words, reading level)
4. Library / History — past stories, re-generate, export (PDF / MD)
5. Settings — locale, theme, billing/plan, token usage dashboard

### Internationalisation
- Multilingual generation native to LLMs (locale field on request/personality)
- react-i18next + RTL support (Arabic, Hebrew)
- SSLCommerz handles BDT; international payments also supported by SSLCommerz
- Per-locale content moderation in Supervisor node (especially for children audience)
- AWS Bedrock / Google Vertex in-region for data residency (GDPR, India DPDP)

---

## What Has NOT Been Built Yet (Continue From Here)

### Priority 1 — LangGraph Implementation (START HERE)
- [ ] Define TypedDict state schema:
      fields: topic, tone, audience, constraints, personality, research[], light_bullets[],
      dark_bullets[], facts[], story_draft, final_output, token_usage, metadata
- [ ] Build StateGraph: nodes, edges, conditional routing, fan-out, fan-in
- [ ] Personality Injector node (loads preset from Postgres, injects into writer system prompt)
- [ ] Wire Checkpointer (Redis backend via langgraph-checkpoint-redis)
- [ ] Streaming via graph.astream_events → FastAPI SSE endpoint

### Priority 2 — Backend / API
- [ ] FastAPI app: POST /api/stories/generate (SSE), GET /api/stories/{id}
- [ ] POST /api/personalities, GET /api/personalities, PUT, DELETE
- [ ] POST /api/payment/initiate → SSLCommerz session creation
- [ ] POST /api/payment/ipn → IPN webhook handler (payment confirmation)
- [ ] GET /api/payment/success, /api/payment/fail, /api/payment/cancel (redirect URLs)
- [ ] LiteLLM proxy config (model aliases: haiku-tier, sonnet-tier, opus-tier)
- [ ] LangSmith tracing integration

### Priority 3 — SSLCommerz Payment Integration
- [ ] backend/app/payment/sslcommerz.py — session initiation, IPN validation
- [ ] Plan management: Free (5 stories/mo), Pro (BDT 499/mo), Enterprise (BDT 1,499/mo)
- [ ] IPN signature validation (MD5 hash check)
- [ ] Transaction status endpoint

### Priority 4 — Frontend
- [ ] Config Panel component (React)
- [ ] Live generation view (multi-panel SSE consumer, each panel streams independently)
- [ ] Personality Manager CRUD
- [ ] Token/cost meter component (live during generation)
- [ ] Billing/plan upgrade page (SSLCommerz payment initiation)

### Priority 5 — Data Layer
- [ ] Postgres schema (users, personalities, stories, runs, payments)
- [ ] pgvector setup for RAG embeddings + semantic cache
- [ ] Redis config for LangGraph checkpointer + semantic cache (embedding lookup)
- [ ] Alembic migrations

### Priority 6 — Deployment to storyteller.techvigilant.com
- [ ] docker-compose.prod.yml (no --reload, nginx sidecar, production env)
- [ ] Add DNS record in Cloudflare (see docs/cloudflare-tunnel.md)
- [ ] Update Cloudflare Tunnel config on ZimaOS with storyteller ingress rule
- [ ] Add GitHub secrets (ZIMAOS_HOST, ZIMAOS_USER, ZIMAOS_SSH_KEY)
- [ ] First production deploy

---

## How to Continue This Session

1. **Check the priority list above** — always start at the highest incomplete priority.
2. **Show actual code** — Abrar wants real implementation files, not pseudocode.
3. **Docker-first** — every new service needs a Dockerfile or docker-compose entry.
4. **Feature branch per task** — remind Abrar to push after each feature:
   `git add . && git commit -m "feat: <what-was-built>" && git push origin <branch>`
5. **Token cost callout** — whenever a design affects token usage, quantify it.
6. **Excalidraw** — restore checkpoint `a14d54ee574840d5a5` to add to existing architecture diagram.
7. **SSLCommerz not Stripe** — never suggest Stripe; SSLCommerz is the payment gateway.

### Suggested opening when resuming:
> "Story Engine architecture is complete and the project folder is live at
> E:\Code\Projects\story-engine with git initialised, GitHub Actions CI/CD wired,
> and docs for the Cloudflare Tunnel deployment at storyteller.techvigilant.com.
> Ready to build — starting with Priority 1: the LangGraph StateGraph.
> Shall I write the state schema and supervisor node first?"

---

## Quick Reference
| Item | Value |
|---|---|
| Excalidraw checkpoint | a14d54ee574840d5a5 |
| Cloudflare Zone ID | c1f525bdc6a810b8bdba76c6716f6276 |
| Live URL | https://storyteller.techvigilant.com |
| Project folder (Windows) | E:\Code\Projects\story-engine |
| Project folder (ZimaOS) | /DATA/AppData/story-engine |
| ZimaOS IP | 192.168.0.127 |
| Payment gateway | SSLCommerz (sslcommerz.com) |
| Primary market | Bangladesh (BDT pricing) |
| Model router | LiteLLM proxy |
| Tracing | LangSmith |
| Primary constraint | Context token spend optimisation |
| Core pattern | LangGraph supervisor → parallel Haiku agents → Sonnet writer/synthesizer |
