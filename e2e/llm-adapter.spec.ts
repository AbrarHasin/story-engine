/**
 * LLM adapter capability tests — provider switching (Claude API ⇄ local Docker model).
 *
 * Covers:
 *   1. /api/v1/llm/config exposes the active adapter (provider + role→model map)
 *   2. Local provider is configured with Gemma 3 4B (ai/gemma3:4B)
 *   3. OpenAPI schema includes the new LLM endpoints
 *   4. Docker Model Runner serves the model on its OpenAI-compatible endpoint
 *   5. /api/v1/llm/ping performs one real inference through the active adapter
 *   6. Full story generation runs end-to-end through the local model (SSE)
 *   7. Local inference is accounted at $0 cost
 */
import { test, expect } from '@playwright/test';

const API = 'http://127.0.0.1:8080';
const DMR_HOST = 'http://127.0.0.1:12434'; // Docker Model Runner host TCP endpoint

// Shared state — safe because workers: 1
let provider = '';
let localModel = '';
let authToken = '';

// ── 1–2. Adapter config ───────────────────────────────────────────────────────

test('llm config endpoint reports active adapter', async ({ request }) => {
  const r = await request.get(`${API}/api/v1/llm/config`);
  expect(r.status()).toBe(200);
  const body = await r.json();

  expect(['anthropic', 'local']).toContain(body.provider);
  for (const role of ['router', 'writer', 'synthesizer', 'premium']) {
    expect(body.models[role], `missing model for role: ${role}`).toBeTruthy();
  }

  provider = body.provider;
  localModel = body.models.router;
  console.log('Active adapter:', JSON.stringify(body));
});

test('local gemma3 4B provider is configured', async ({ request }) => {
  const r = await request.get(`${API}/api/v1/llm/config`);
  const body = await r.json();

  expect(body.provider, 'expected LLM_PROVIDER=local (Docker Model Runner)').toBe('local');
  expect(body.models.router.toLowerCase()).toContain('gemma');
  expect(body.base_url, 'local adapter must expose its endpoint').toBeTruthy();
  expect(body.base_url).toMatch(/\/v1$/);

  // One local model serves every role
  const models = Object.values(body.models) as string[];
  expect(new Set(models).size).toBe(1);
  console.log(`Local model: ${body.models.router} @ ${body.base_url}`);
});

// ── 3. OpenAPI surface ────────────────────────────────────────────────────────

test('openapi schema includes llm adapter endpoints', async ({ request }) => {
  const r = await request.get(`${API}/openapi.json`);
  expect(r.status()).toBe(200);
  const paths = Object.keys((await r.json()).paths);
  expect(paths).toContain('/api/v1/llm/config');
  expect(paths).toContain('/api/v1/llm/ping');
});

// ── 4. Docker Model Runner direct ────────────────────────────────────────────

test('docker model runner serves the configured model on OpenAI-compatible endpoint', async ({ request }) => {
  test.skip(provider !== 'local', 'only relevant for the local provider');

  let r;
  try {
    r = await request.get(`${DMR_HOST}/engines/v1/models`, { timeout: 15_000 });
  } catch {
    test.skip(true, 'DMR host TCP (12434) not enabled — backend reaches it via the internal socket');
    return;
  }
  expect(r.status()).toBe(200);
  const body = await r.json();
  const ids = (body.data ?? []).map((m: any) => m.id);
  console.log('DMR models:', ids.join(', '));
  // Compare against the model the adapter is configured with (e.g. ai/gemma3:4B)
  const want = localModel.toLowerCase().replace(/^(docker\.io\/)/, '');
  expect(ids.some((id: string) => id.toLowerCase().includes(want))).toBe(true);
});

// ── 5. Real inference smoke test ─────────────────────────────────────────────

test('register user for adapter e2e', async ({ request }) => {
  const email = `e2e-llm-${Date.now()}@test.com`;
  const r = await request.post(`${API}/api/v1/auth/register`, {
    data: { email, password: 'testpassword123', name: 'LLM Adapter E2E' },
  });
  expect(r.status()).toBe(201);
  authToken = (await r.json()).access_token;
  console.log(`Registered: ${email}`);
});

test('llm ping requires auth', async ({ request }) => {
  const r = await request.post(`${API}/api/v1/llm/ping`);
  expect([401, 403]).toContain(r.status());
});

test('llm ping runs one real inference through the adapter', async ({ request }) => {
  test.skip(!authToken, 'requires register test to run first');
  test.setTimeout(330_000); // first call loads the model into memory

  const r = await request.post(`${API}/api/v1/llm/ping`, {
    headers: { Authorization: `Bearer ${authToken}` },
    timeout: 320_000,
  });
  expect(r.status(), 'LLM must be reachable through the adapter').toBe(200);
  const body = await r.json();

  expect(body.ok).toBe(true);
  expect(body.provider).toBe(provider || body.provider);
  expect((body.reply ?? '').length).toBeGreaterThan(0);
  console.log(`Ping via ${body.provider} (${body.model}): "${body.reply}"`);
});

// ── 6. End-to-end story generation through the local model ──────────────────

test('generate story end-to-end via active adapter', async ({ request }) => {
  test.skip(!authToken, 'requires register test to run first');
  test.setTimeout(900_000); // local CPU inference across 7 graph nodes is slow

  const start = Date.now();
  const resp = await request.post(`${API}/api/v1/stories/generate`, {
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${authToken}`,
    },
    data: {
      topic: 'A robot learns to paint',
      tonality: 'whimsical',
      audience: 'general',
      length: 'short',
      locale: 'en',
      include_light: true,
      include_dark: false,
      include_facts: false,
    },
    timeout: 880_000,
  });

  expect(resp.status()).toBe(200);
  expect(resp.headers()['content-type']).toContain('text/event-stream');

  const body = await resp.text();
  const events: { type: string; data: any }[] = [];
  let current = '';
  for (const line of body.split('\n')) {
    if (line.startsWith('event: ')) current = line.slice(7).trim();
    else if (line.startsWith('data: ')) {
      try { events.push({ type: current, data: JSON.parse(line.slice(6)) }); } catch { /* ignore */ }
    }
  }

  console.log(`Events: ${events.map(e => e.type).join(', ')}`);

  const errorEvent = events.find(e => e.type === 'error');
  if (errorEvent) throw new Error(`Generation failed: ${errorEvent.data.message}`);

  expect(events.find(e => e.type === 'start'), 'missing start event').toBeTruthy();
  const done = events.find(e => e.type === 'done');
  expect(done, 'missing done event').toBeTruthy();

  const nodes = events.filter(e => e.type === 'node_complete').map(e => e.data.node);
  expect(nodes).toContain('research');
  expect(nodes).toContain('writer');
  expect(nodes).toContain('synthesizer');

  const writerEvent = events.find(e => e.type === 'node_complete' && e.data.node === 'writer');
  expect((writerEvent?.data.draft ?? '').length, 'writer must produce a draft').toBeGreaterThan(50);

  // 7. Local inference must be free
  if (provider === 'local') {
    expect(done!.data.tokens.cost_usd).toBe(0);
    console.log(`Local inference cost: $${done!.data.tokens.cost_usd} (tokens in/out: ${done!.data.tokens.input}/${done!.data.tokens.output})`);
  }

  console.log(`Story generated via '${provider}' in ${((Date.now() - start) / 1000).toFixed(1)}s`);
});
