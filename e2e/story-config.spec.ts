/**
 * Story config-combination tests — verifies the generated output actually
 * honors the request configuration:
 *
 *   Structural (deterministic):
 *     - include_light / include_dark / include_facts toggle the corresponding
 *       graph nodes on/off (asserted via SSE node_complete events)
 *     - writer draft contains the mandated ## section structure
 *     - locale=en output is English text
 *
 *   Semantic (LLM-as-judge via the local model):
 *     - final output's tone resembles the requested tonality
 *     - final output suits the requested audience
 *       (judged 1–5 by the active local model; pass threshold ≥ 3)
 *
 * Runs 4 real generations across distinct tonality × audience × length ×
 * flag combinations.
 */
import { test, expect } from '@playwright/test';

const API = 'http://127.0.0.1:8080';
const DMR = 'http://127.0.0.1:12434/engines/v1';

// Shared state — safe because workers: 1
let authToken = '';
let judgeModel = '';
let provider = '';

// ── Helpers ───────────────────────────────────────────────────────────────────

interface GenResult {
  nodes: string[];
  draft: string;
  final: string;
  costUsd: number;
}

async function generate(request: any, config: Record<string, any>): Promise<GenResult> {
  const resp = await request.post(`${API}/api/v1/stories/generate`, {
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${authToken}`,
    },
    data: config,
    timeout: 850_000,
  });
  expect(resp.status()).toBe(200);

  const body = await resp.text();
  const events: { type: string; data: any }[] = [];
  let current = '';
  for (const line of body.split('\n')) {
    if (line.startsWith('event: ')) current = line.slice(7).trim();
    else if (line.startsWith('data: ')) {
      try { events.push({ type: current, data: JSON.parse(line.slice(6)) }); } catch { /* ignore */ }
    }
  }

  const errorEvent = events.find(e => e.type === 'error');
  if (errorEvent) throw new Error(`Generation failed: ${errorEvent.data.message}`);
  expect(events.find(e => e.type === 'done'), 'missing done event').toBeTruthy();

  const nodes = events.filter(e => e.type === 'node_complete').map(e => e.data.node);
  const draft = events.find(e => e.type === 'node_complete' && e.data.node === 'writer')?.data.draft ?? '';
  const final = events.find(e => e.type === 'node_complete' && e.data.node === 'synthesizer')?.data.final ?? '';
  const costUsd = events.find(e => e.type === 'done')?.data.tokens.cost_usd ?? -1;
  return { nodes, draft, final, costUsd };
}

function tolerantJson(text: string): any {
  let t = text.trim();
  const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) t = fence[1].trim();
  const start = t.indexOf('{');
  const end = t.lastIndexOf('}');
  if (start !== -1 && end > start) t = t.slice(start, end + 1);
  return JSON.parse(t);
}

/** Ask the local model to judge tone/audience fit, 1–5 each. One retry on parse failure. */
async function judgeStory(request: any, story: string, tonality: string, audience: string) {
  const prompt =
    `You are a literary evaluator. Read the story below, then rate it on two scales from 1 (not at all) to 5 (perfectly):\n` +
    `- tone: how well the writing style matches the tone "${tonality}"\n` +
    `- audience: how appropriate the language and content are for the audience "${audience}"\n\n` +
    `Reply with ONLY a JSON object, no other text: {"tone": N, "audience": N}\n\n` +
    `STORY:\n${story.slice(0, 6000)}`;

  for (let attempt = 1; attempt <= 2; attempt++) {
    const r = await request.post(`${DMR}/chat/completions`, {
      data: {
        model: judgeModel,
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 60,
        temperature: 0,
      },
      timeout: 300_000,
    });
    expect(r.status(), 'judge model must be reachable').toBe(200);
    const content = (await r.json()).choices?.[0]?.message?.content ?? '';
    try {
      const scores = tolerantJson(content);
      return { tone: Number(scores.tone), audience: Number(scores.audience) };
    } catch {
      console.log(`  judge reply unparseable (attempt ${attempt}): ${content.slice(0, 120)}`);
    }
  }
  throw new Error('judge model returned unparseable output twice');
}

const base = { length: 'short', locale: 'en' };

// ── Setup ─────────────────────────────────────────────────────────────────────

test('setup: register user and detect judge model', async ({ request }) => {
  const email = `e2e-config-${Date.now()}@test.com`;
  const r = await request.post(`${API}/api/v1/auth/register`, {
    data: { email, password: 'testpassword123', name: 'Config Matrix E2E' },
  });
  expect(r.status()).toBe(201);
  authToken = (await r.json()).access_token;

  const cfg = await (await request.get(`${API}/api/v1/llm/config`)).json();
  provider = cfg.provider;
  judgeModel = cfg.provider === 'local' ? cfg.models.router : '';
  console.log(`Provider: ${provider} | Judge model: ${judgeModel || 'n/a'}`);
});

// ── Combo 1: humorous × children × all sections ──────────────────────────────

test('humorous story for children — structure + tone/audience resemblance', async ({ request }) => {
  test.setTimeout(900_000);
  const cfg = {
    ...base,
    topic: 'A penguin who is afraid of cold water',
    tonality: 'humorous',
    audience: 'children',
    include_light: true,
    include_dark: true,
    include_facts: true,
  };
  const res = await generate(request, cfg);

  // All optional nodes must have run
  for (const n of ['research', 'light_side', 'dark_side', 'facts', 'writer', 'synthesizer']) {
    expect(res.nodes, `node ${n} should run`).toContain(n);
  }
  // Writer draft must follow the mandated section structure
  for (const section of ['## Light Side', '## Dark Side', '## Interesting Facts', '## The Story']) {
    expect(res.draft, `draft must contain "${section}"`).toContain(section);
  }
  expect(res.final.length).toBeGreaterThan(100);

  test.skip(provider !== 'local', 'LLM judge requires the local provider');
  const scores = await judgeStory(request, res.final, cfg.tonality, cfg.audience);
  console.log(`humorous/children scores: ${JSON.stringify(scores)}`);
  expect(scores.tone, 'tone should resemble "humorous"').toBeGreaterThanOrEqual(3);
  expect(scores.audience, 'should suit "children"').toBeGreaterThanOrEqual(3);
});

// ── Combo 2: dramatic × experts × light disabled ─────────────────────────────

test('dramatic story for experts, no light side — flags + resemblance', async ({ request }) => {
  test.setTimeout(900_000);
  const cfg = {
    ...base,
    topic: 'The collapse of a deep-sea research station',
    tonality: 'dramatic',
    audience: 'experts',
    length: 'medium',
    include_light: false,
    include_dark: true,
    include_facts: true,
  };
  const res = await generate(request, cfg);

  expect(res.nodes, 'light_side must NOT run when include_light=false').not.toContain('light_side');
  expect(res.nodes).toContain('dark_side');
  expect(res.nodes).toContain('facts');
  expect(res.final.length).toBeGreaterThan(100);

  test.skip(provider !== 'local', 'LLM judge requires the local provider');
  const scores = await judgeStory(request, res.final, cfg.tonality, cfg.audience);
  console.log(`dramatic/experts scores: ${JSON.stringify(scores)}`);
  expect(scores.tone, 'tone should resemble "dramatic"').toBeGreaterThanOrEqual(3);
  expect(scores.audience, 'should suit "experts"').toBeGreaterThanOrEqual(3);
});

// ── Combo 3: inspirational × general × only light ────────────────────────────

test('inspirational story, only light side — flags + resemblance', async ({ request }) => {
  test.setTimeout(900_000);
  const cfg = {
    ...base,
    topic: 'A village that planted a forest over 30 years',
    tonality: 'inspirational',
    audience: 'general',
    include_light: true,
    include_dark: false,
    include_facts: false,
  };
  const res = await generate(request, cfg);

  expect(res.nodes).toContain('light_side');
  expect(res.nodes, 'dark_side must NOT run when include_dark=false').not.toContain('dark_side');
  expect(res.nodes, 'facts must NOT run when include_facts=false').not.toContain('facts');
  expect(res.final.length).toBeGreaterThan(100);

  test.skip(provider !== 'local', 'LLM judge requires the local provider');
  const scores = await judgeStory(request, res.final, cfg.tonality, cfg.audience);
  console.log(`inspirational/general scores: ${JSON.stringify(scores)}`);
  expect(scores.tone, 'tone should resemble "inspirational"').toBeGreaterThanOrEqual(3);
  expect(scores.audience, 'should suit "general"').toBeGreaterThanOrEqual(3);
});

// ── Combo 4: neutral × executives × only facts (structural + cost) ───────────

test('neutral story for executives, facts only — flags + zero local cost', async ({ request }) => {
  test.setTimeout(900_000);
  const cfg = {
    ...base,
    topic: 'Quarterly risks of supply chain automation',
    tonality: 'neutral',
    audience: 'executives',
    include_light: false,
    include_dark: false,
    include_facts: true,
  };
  const res = await generate(request, cfg);

  expect(res.nodes).toContain('facts');
  expect(res.nodes).not.toContain('light_side');
  expect(res.nodes).not.toContain('dark_side');
  expect(res.final.length).toBeGreaterThan(100);

  // English locale sanity: output is mostly ASCII/latin text
  const latinRatio = (res.final.match(/[A-Za-z\s.,'"!?()\-:;0-9]/g) ?? []).length / res.final.length;
  expect(latinRatio, 'locale=en output should be English text').toBeGreaterThan(0.85);

  if (provider === 'local') expect(res.costUsd).toBe(0);
});
