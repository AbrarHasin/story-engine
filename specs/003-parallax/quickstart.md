# Quickstart: Parallax (003), local Docker

Target state after Phase 1 (MVP). Nothing here runs yet; this is the acceptance script the build must satisfy. It mirrors the pilot's local stack (Story Engine PR #18 `scripts/local-up.sh`).

## 1. Prerequisites

- Docker Desktop (WSL2), Node 22, Python 3.12.
- `backend/.env` from `backend/.env.example`. Keys, all optional for a mocked run:
  - `LLM_PROVIDER=local` (zero cost, Docker Model Runner) or `anthropic` with `ANTHROPIC_API_KEY` (spend-capped, needs the human's go).
  - `FACTCHECK_TOOLS_API_KEY` (Google Cloud, free), `COURTLISTENER_TOKEN` (free account). Without them those connectors report `degraded` and the report still builds.
  - `PARALLAX_USER_AGENT="ParallaxBot/0.1 (+https://<domain>/bot)"`.
- Never commit `backend/.env`.

## 2. Start

```bash
scripts/local-up.sh            # postgres, redis, langfuse, api, graph, ingest, frontend
curl -s localhost:8080/health  # {"status":"ok", db, redis, langfuse, ingest_last_cycle}
docker compose exec api python -m app.sources.import_directory \
  --directory /vault/Knowledge/News-Sources/Global-News-RSS-API-Directory.md \
  --extra /hive/research/news-feeds-additions-2026-10-16.json      # ~235 feeds, tiers, state flags
docker compose exec ingest python -m app.workers.ingest --once      # first cycle (<= 5 min)
```

## 3. Mocked end-to-end (CI equivalent, $0)

```bash
cd backend && .venv/bin/pytest -q                          # unit + contract + cassette integration
.venv/bin/pytest tests/contract -q                          # openapi.yaml + sse-events.schema.json
cd .. && ./node_modules/.bin/playwright test e2e/report.spec.ts e2e/trust.spec.ts
```

Expected (`report.spec.ts`, fixture topic "Michael Jackson allegations", mocked LLM, recorded HTTP):

1. Stream order: `start` -> `topic` (type `historical`, span 1993-) -> `stage` events -> `timeline` (>= 6 events incl. 1993, 2005, 2019) -> `perspective` x >= 2 -> `claim` x >= 3 -> `rating` per claim -> `section` -> `done`.
2. Every `rating.evidence[].url` is in `report_articles` and every quote is found verbatim in the stored text (validator report all green).
3. A living-person allegation claim arrives as `rating.status = published` with `assessment_label`, attributive reason wording and, for `verified` / `false`, two independent strong families.
4. Repeat the same topic: `start.cache_hit = true`, `done.tokens.cost_usd = 0`.

## 4. Real-LLM smoke (only with the human's explicit spend approval)

```bash
LLM_PROVIDER=anthropic SPEND_CAP_USD=0.05 \
  backend/.venv/bin/python -m app.tools.smoke_report "Michael Jackson controversy"
```

Prints per-stage tokens and cost; aborts if the running total passes `SPEND_CAP_USD`. Expected about $0.006 per cold report (research R7).

## 5. Evaluation (manual, budgeted)

```bash
backend/.venv/bin/python -m tests.eval.run --gold tests/eval/gold/claims.jsonl --limit 300 --spend-cap 0.30
backend/.venv/bin/python -m tests.eval.run --redteam tests/eval/redteam/topics.yaml --spend-cap 0.15
```

Writes `tests/eval/out/<date>/metrics.json`: exact / within-one agreement, macro-F1, inversion rate, ECE, citation validity, unsupported-sentence rate, living-person attribution compliance, cost, latency. Gate for public launch: SC-002..SC-005.

## 6. Stop

```bash
scripts/local-down.sh            # keep volumes
scripts/local-down.sh --destroy  # drop volumes (articles, ratings, audit) - local only
```
