# Story Engine architecture

One generated Excalidraw file with seven views, kept next to the code it describes.

- **Open it:** `story-engine-architecture.excalidraw` in [excalidraw.com](https://excalidraw.com)
  (File, Open) or the Excalidraw VS Code extension. Each view is a frame; use the frame list
  on the left or zoom to a frame.
- **Do not edit it by hand.** It is a build artifact of `generate.py`. A change made in the
  Excalidraw GUI is lost on the next regeneration; port it into the script instead.
- **Which code it describes:** branch `llm-adapter` at `c2db465`. The LLM adapter, the
  `LLM_PROVIDER` switch and Docker Model Runner live on that branch and are not on `master`
  yet, so views 1 to 3 and 5 show them as live.

## How to read it

Flat style, labelled trust boundaries, one colour per flow.

| Convention | Meaning |
|---|---|
| Status chip on a card | `LIVE` in the code and running, `PARTIAL` exists but incomplete, `PLANNED` designed not built, `DEFERRED` decided and postponed, `BLOCKED` waiting on a decision |
| Dashed card or line | Not built yet |
| Line colour | Blue request and SSE, clay model calls, steel-blue database and cache, magenta traces, green payments, violet CI and operations |
| Numbered badge | A step of one story request, explained in the step panel of view 2 |
| Boundary with a tab | Trust boundary: Internet, Cloudflare, Docker host, Compose network, Docker Model Runner |

| View | What it answers |
|---|---|
| 1 System context (C4 level 1) | Who and what Story Engine talks to, and the four decisions that shaped it |
| 2 Containers and flow (C4 level 2) | Every container inside its trust boundary, and the 10 steps of one request |
| 3 LangGraph pipeline | Eight nodes, model per node, fan-out and fan-in, `StoryState` keys, the `LLM_PROVIDER` switch |
| 4 Data model | Four tables, keys, Alembic revisions, where Redis and pgvector fit |
| 5 Cost per story | Token cost at the `max_tokens` ceiling and which savings levers are live |
| 6 Well-Architected review | Six pillars plus the Generative AI lens, and the risk register linked to issues #1 to #12 |
| 7 Remediation roadmap | Waves 1 to 3 and the blocked items |

## The shape of it

FastAPI streams, LangGraph fans out, a role adapter picks the model, Langfuse watches.

| Zone | Runs |
|---|---|
| Browser | React + Vite SPA, Zustand store, fetch-based SSE consumer |
| Cloudflare | DNS and Tunnel for `storyteller.techvigilant.com` (prod deploy pending) |
| Docker host | nginx (prod only), FastAPI, Postgres 16 + pgvector, Redis 7, Langfuse v3 (6 containers) |
| Anthropic | Haiku 4.5 for routing and sub-agents, Sonnet 4.6 for writer and synthesizer |
| Docker Model Runner | `ai/gemma3:4B` on the host GPU, every role, $0 per story |
| SSLCommerz | Plan upgrades, sandbox until `SSLCOMMERZ_SANDBOX=false` |

Custom code is one FastAPI app, eight graph nodes and one adapter module. The application has
no scheduler; CI, the local deploy hook, the Langfuse worker and cloudflared are the only
unattended jobs.

## One story request (steps 1 to 10 in view 2)

1. Browser POSTs the topic and options through the Cloudflare Tunnel.
2. The tunnel hands the request to nginx on port 80.
3. nginx proxies `/api` to FastAPI with buffering off and 300 s timeouts.
4. FastAPI checks the JWT, compiles the personality prompt and inserts a `stories` row with
   status `running`.
5. It invokes the compiled graph with `thread_id = story_id`.
6. Supervisor, then research, light, dark and facts run in parallel on the `router` role (Haiku).
7. Writer then synthesizer run on Sonnet.
8. A Langfuse callback attached to the run ships the trace.
9. Each node end becomes an SSE `node_complete` event; at the end the story row is updated
   with text, tokens and cost.
10. A final `done` event carries totals and the trace URL.

Letter `P` in view 2 is the payment path: initiate redirects to SSLCommerz, the IPN webhook
confirms and updates `users.plan`.

## Decisions

- **Models by role, not by node.** Nodes call `get_adapter().chat(role, ...)`; the adapter owns
  model names and prices. One env var swaps providers and no node imports a provider SDK.
- **Cheap fan-out, premium writing.** Five short Haiku calls and two Sonnet calls, each with a
  hard `max_tokens` cap in `core/config.py`. Ceiling near $0.04 per story.
- **SSE over polling.** Per-node events let the UI fill in as agents finish.
- **Self-hosted tracing.** Langfuse v3 replaced LangSmith: no usage limits.
- **Local model as a first-class provider.** `LLM_PROVIDER=local` runs the whole pipeline on
  Docker Model Runner.

## Risks

The register in view 6 uses these issue numbers. All 12 were open on 2026-10-15.

| # | Severity | What | Schedule |
|---|---|---|---|
| 1 | Critical | Story and personality read, update, delete are unauthenticated and not owner-scoped | Wave 1 |
| 2 | Critical | Payments: upgrades credit the dev user, initiate unauthenticated, IPN signature optional, no validation call | Wave 1 |
| 3 | High | Prod auth incoherent: SPA sends no token, secret differs from dev, no startup guard | Blocked (Auth0) |
| 4 | High | Synthesizer capped at 500 tokens but must return the 1500-token story: truncated | Wave 1 |
| 5 | High | Supervisor call wasted (route ignored) and its tokens missing from cost | Wave 1 |
| 6 | Medium | Prompt caching and semantic cache promised but absent; $0.19 target unmeasured | Wave 1 (caching), wave 2 (semantic) |
| 7 | Medium | Prod compose hard-codes Langfuse dev keys and a default DB password | Wave 3 |
| 8 | Medium | `stories.research` never persisted; export omits research | Wave 3 |
| 9 | Medium | Quotas and rate limits absent: free-plan spend unbounded | Wave 3 |
| 10 | Low | Langfuse `user_id` is the story id; trace URL built from `run_id` | Wave 3 |
| 11 | Low | Doc drift: astream vs astream_events, ports, gemma tag, test counts | Wave 3 |
| 12 | Low | Generator uses a request-scoped DB session after the handler returns; `utcnow()` deprecated | Wave 3 |

Found while drawing, no issue number yet: **T1** prod compose leaves `LLM_PROVIDER=local`,
**T2** no timeout or retry on model calls (roadmap wave 2), **T3** Redis checkpointer falls
back to stateless silently, **T4** topic and personality go straight into prompts with no
output filter.

## Remediation roadmap (view 7)

| Wave | Work | Why here |
|---|---|---|
| 1 | #1 auth and owner scoping, #2 payment integrity, #4 and #5 truncation and wasted call, then prompt caching (half of #6) | Data exposure and money first; count correctly before optimising cost |
| 2 | Semantic cache (needs the `embedding` column fixed), timeouts and retry (T2), LiteLLM keep or drop | Measured against the corrected wave 1 baseline |
| 3 | #7 to #12 | Hygiene and drift |
| Blocked | #3 login UI or Auth0, production deploy | Auth0 decision; proposed gate: no public deploy until #1, #2 and #3 are closed |

## Regenerate

```bash
python docs/architecture/generate.py     # or: make diagrams
```

Python 3, standard library only (tested on 3.12). The RNG is seeded (`20261015`), so an unchanged
script writes a byte-identical file; the script exits with an error if any card's text is
wider than its box. When you change the topology or the register:

1. Edit `generate.py` (cards, flows, register rows). Shared drawing primitives are in
   `story_diagram_kit.py`.
2. Run the generator and commit the script and the `.excalidraw` together.
3. Open the file in Excalidraw and look at each frame before merging.

## Files

| File | Role |
|---|---|
| `generate.py` | Source of truth for the seven views |
| `story_diagram_kit.py` | Palette, cards, boundaries, chips, connectors, frames |
| `story-engine-architecture.excalidraw` | Generated output, do not hand-edit |
