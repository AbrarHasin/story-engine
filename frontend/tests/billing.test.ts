// Unit tests for src/lib/billing.ts with a mocked API. Run: npm run test:unit
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  canUpgrade, clearPendingPlan, describeGenerateFailure, fetchMe, fetchPaymentStatus, fetchPlans, formatBdt,
  isSafeGatewayUrl, parsePlans, planFeatures, planName, pollPaymentStatus, quotaSummary, readPendingPlan,
  readTranId, savePendingPlan, startCheckout, PaymentStatusError, type Fetcher,
} from '../src/lib/billing.ts'

interface Call { path: string; init?: RequestInit }

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function mockApi(status: number, body: unknown): { fetcher: Fetcher; calls: Call[] } {
  const calls: Call[] = []
  const fetcher: Fetcher = async (path, init) => {
    calls.push({ path, init })
    return json(status, body)
  }
  return { fetcher, calls }
}

/** Answers each call with the next response in the list (the last one repeats). */
function sequenceApi(responses: Array<() => Response>): { fetcher: Fetcher; calls: Call[] } {
  const calls: Call[] = []
  const fetcher: Fetcher = async (path, init) => {
    calls.push({ path, init })
    return responses[Math.min(calls.length - 1, responses.length - 1)]()
  }
  return { fetcher, calls }
}

/** Fake clock: sleep advances time instantly. */
function fakeClock() {
  let t = 0
  const sleeps: number[] = []
  return {
    now: () => t,
    sleep: async (ms: number) => { sleeps.push(ms); t += ms },
    sleeps,
  }
}

function memoryStore() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
  }
}

const PLANS_BODY = {
  currency: 'BDT',
  plans: [
    { id: 'free', name: 'Free', price_bdt: 0, stories_per_month: 10 },
    { id: 'pro', name: 'Pro', price_bdt: 499, stories_per_month: 200 },
    { id: 'enterprise', name: 'Enterprise', price_bdt: 1499, stories_per_month: 0 },
  ],
}

const payment = (status: string) => ({
  tran_id: 'SE-ABC123', status, plan: 'pro', amount: 499, currency: 'BDT',
  confirmed_at: status === 'confirmed' ? '2026-10-17T10:00:00Z' : null,
})

// ── plans ────────────────────────────────────────────────────────────────────

test('fetchPlans reads GET /api/v1/payment/plans', async () => {
  const { fetcher, calls } = mockApi(200, PLANS_BODY)
  const plans = await fetchPlans(fetcher)
  assert.equal(calls[0].path, '/api/v1/payment/plans')
  assert.deepEqual(
    plans.map((p) => [p.id, p.name, p.priceBdt, p.storiesPerMonth]),
    [['free', 'Free', 0, 10], ['pro', 'Pro', 499, 200], ['enterprise', 'Enterprise', 1499, 0]],
  )
})

test('plan features come from stories_per_month, 0 = unlimited', async () => {
  const plans = parsePlans(PLANS_BODY)
  assert.equal(plans[0].features[0], '10 stories a month')
  assert.equal(plans[1].features[0], '200 stories a month')
  assert.equal(plans[2].features[0], 'Unlimited stories')
  assert.equal(planFeatures(1)[0], '1 story a month')
  assert.equal(planFeatures(5000)[0], '5,000 stories a month')
})

test('plans use server values, sorted, skipping unknown or malformed rows', () => {
  const plans = parsePlans({
    plans: [
      { id: 'enterprise', name: 'Business', price_bdt: 2999, stories_per_month: 0 },
      { id: 'gold', name: 'Gold', price_bdt: 1, stories_per_month: 1 },
      { id: 'pro', name: 'Pro', price_bdt: 'cheap', stories_per_month: 50 },
      { id: 'free', name: '', price_bdt: 0, stories_per_month: 3 },
    ],
  })
  assert.deepEqual(
    plans.map((p) => [p.id, p.name, p.priceBdt, p.storiesPerMonth]),
    [['free', 'Free', 0, 3], ['enterprise', 'Business', 2999, 0]],
  )
  assert.equal(planName('enterprise', plans), 'Business')
  assert.equal(planName('pro', plans), 'Pro')
  assert.equal(planName('pro'), 'Pro')
})

test('a plan list with nothing usable is an error', async () => {
  assert.throws(() => parsePlans({ plans: [] }), /no plans/)
  assert.throws(() => parsePlans({ currency: 'BDT' }), /Unexpected plan list/)
  await assert.rejects(fetchPlans(mockApi(500, { detail: 'Boom' }).fetcher), /Boom/)
  await assert.rejects(fetchPlans(async () => { throw new TypeError('fetch failed') }), /Could not reach/)
})

test('only higher paid plans are upgrades', () => {
  assert.equal(canUpgrade('free', 'pro'), true)
  assert.equal(canUpgrade('free', 'enterprise'), true)
  assert.equal(canUpgrade('pro', 'enterprise'), true)
  assert.equal(canUpgrade('pro', 'pro'), false)
  assert.equal(canUpgrade('enterprise', 'pro'), false)
  assert.equal(canUpgrade('pro', 'free'), false)
})

test('prices format in taka', () => {
  assert.equal(formatBdt(0), 'Free')
  assert.equal(formatBdt(1499), 'BDT 1,499')
})

// ── quota (server numbers) ───────────────────────────────────────────────────

test('quota summary for a limited plan', () => {
  assert.deepEqual(quotaSummary(4, 10), { used: 4, limit: 10, unlimited: false, remaining: 6, percent: 40 })
})

test('quota summary clamps at the limit', () => {
  const q = quotaSummary(12, 10)
  assert.equal(q.remaining, 0)
  assert.equal(q.percent, 100)
})

test('plan_limit 0 is unlimited', () => {
  const q = quotaSummary(999, 0)
  assert.equal(q.unlimited, true)
  assert.equal(q.remaining, null)
})

// ── /auth/me ─────────────────────────────────────────────────────────────────

test('fetchMe reads plan, plan_limit and usage from /api/v1/auth/me', async () => {
  const { fetcher, calls } = mockApi(200, {
    id: 'u1', email: 'a@b.test', name: 'A', plan: 'pro', plan_limit: 200,
    stories_this_month: 3, total_tokens_used: 100, created_at: '2026-10-01T00:00:00Z',
  })
  const me = await fetchMe(fetcher)
  assert.equal(calls[0].path, '/api/v1/auth/me')
  assert.equal(me.plan, 'pro')
  assert.equal(me.plan_limit, 200)
  assert.equal(me.stories_this_month, 3)
})

test('fetchMe surfaces the API error detail', async () => {
  const { fetcher } = mockApi(401, { detail: 'Not authenticated' })
  await assert.rejects(fetchMe(fetcher), /Not authenticated/)
})

test('fetchMe rejects an unknown plan or a missing plan_limit', async () => {
  await assert.rejects(fetchMe(mockApi(200, { plan: 'gold', plan_limit: 1 }).fetcher), /Unexpected plan/)
  await assert.rejects(fetchMe(mockApi(200, { plan: 'pro' }).fetcher), /plan limit/)
})

// ── checkout ─────────────────────────────────────────────────────────────────

test('startCheckout posts the plan and returns the SSLCommerz sandbox URL', async () => {
  const url = 'https://sandbox.sslcommerz.com/EasyCheckOut/testcdeadbeef'
  const { fetcher, calls } = mockApi(200, { payment_url: url, tran_id: 'SE-ABC123', amount: 499, currency: 'BDT' })
  const session = await startCheckout('pro', fetcher)
  assert.equal(session.payment_url, url)
  assert.equal(calls[0].path, '/api/v1/payment/initiate')
  assert.equal(calls[0].init?.method, 'POST')
  assert.deepEqual(JSON.parse(String(calls[0].init?.body)), { plan: 'pro' })
})

test('startCheckout surfaces a gateway error', async () => {
  const { fetcher } = mockApi(502, { detail: 'SSLCommerz error: Store Credential Error' })
  await assert.rejects(startCheckout('pro', fetcher), /Store Credential Error/)
})

test('startCheckout refuses a non-https payment URL', async () => {
  const { fetcher } = mockApi(200, { payment_url: 'javascript:alert(1)', tran_id: 'SE-X', amount: 499 })
  await assert.rejects(startCheckout('pro', fetcher), /invalid link/)
})

test('startCheckout reports an unreachable server', async () => {
  const fetcher: Fetcher = async () => { throw new TypeError('fetch failed') }
  await assert.rejects(startCheckout('enterprise', fetcher), /Could not reach the server/)
})

test('gateway URL must be https', () => {
  assert.equal(isSafeGatewayUrl('https://sandbox.sslcommerz.com/x'), true)
  assert.equal(isSafeGatewayUrl('http://sandbox.sslcommerz.com/x'), false)
  assert.equal(isSafeGatewayUrl('not a url'), false)
  assert.equal(isSafeGatewayUrl(undefined), false)
})

// ── payment status polling ───────────────────────────────────────────────────

test('fetchPaymentStatus reads the owner-scoped status endpoint', async () => {
  const { fetcher, calls } = mockApi(200, payment('initiated'))
  const s = await fetchPaymentStatus('SE-ABC123', fetcher)
  assert.equal(calls[0].path, '/api/v1/payment/status/SE-ABC123')
  assert.equal(s.status, 'initiated')
  await assert.rejects(
    fetchPaymentStatus('SE-NOPE', mockApi(404, { detail: 'Payment not found' }).fetcher),
    (err: unknown) => err instanceof PaymentStatusError && err.status === 404,
  )
})

test('polling stops when the payment is confirmed', async () => {
  const clock = fakeClock()
  const seen: string[] = []
  const { fetcher, calls } = sequenceApi([
    () => json(200, payment('initiated')),
    () => json(200, payment('initiated')),
    () => json(200, payment('confirmed')),
  ])
  const out = await pollPaymentStatus('SE-ABC123', fetcher, {
    ...clock, onUpdate: (p) => seen.push(p.status),
  })
  assert.equal(out.kind, 'confirmed')
  assert.equal(out.kind === 'confirmed' && out.payment.plan, 'pro')
  assert.equal(calls.length, 3)
  assert.deepEqual(seen, ['initiated', 'initiated', 'confirmed'])
  assert.deepEqual(clock.sleeps, [2000, 2000])
})

test('polling reports failed and cancelled payments', async () => {
  const failed = await pollPaymentStatus('SE-ABC123', mockApi(200, payment('failed')).fetcher, fakeClock())
  assert.equal(failed.kind, 'failed')
  const cancelled = await pollPaymentStatus('SE-ABC123', mockApi(200, payment('cancelled')).fetcher, fakeClock())
  assert.equal(cancelled.kind, 'cancelled')
})

test('polling gives up after the timeout (about 60 s at 2 s)', async () => {
  const clock = fakeClock()
  const { fetcher, calls } = mockApi(200, payment('initiated'))
  const out = await pollPaymentStatus('SE-ABC123', fetcher, clock)
  assert.equal(out.kind, 'timeout')
  assert.equal(out.kind === 'timeout' && out.payment?.status, 'initiated')
  assert.equal(calls.length, 31)
  assert.ok(clock.now() <= 60000)
})

test('polling stops at once on 404 (unknown or not ours)', async () => {
  const clock = fakeClock()
  const { fetcher, calls } = mockApi(404, { detail: 'Payment not found' })
  const out = await pollPaymentStatus('SE-ABC123', fetcher, clock)
  assert.equal(out.kind, 'not_found')
  assert.equal(calls.length, 1)
  assert.deepEqual(clock.sleeps, [])
})

test('polling retries server and network errors, but not auth errors', async () => {
  let n = 0
  const flaky: Fetcher = async () => {
    n += 1
    if (n === 1) throw new TypeError('fetch failed')
    if (n === 2) return json(503, { detail: 'busy' })
    return json(200, payment('confirmed'))
  }
  const out = await pollPaymentStatus('SE-ABC123', flaky, fakeClock())
  assert.equal(out.kind, 'confirmed')
  assert.equal(n, 3)

  const auth = await pollPaymentStatus('SE-ABC123', mockApi(401, { detail: 'Not authenticated' }).fetcher, fakeClock())
  assert.deepEqual(auth, { kind: 'error', message: 'Not authenticated' })
})

test('polling stops when aborted', async () => {
  const controller = new AbortController()
  const clock = fakeClock()
  const { fetcher, calls } = mockApi(200, payment('initiated'))
  const out = await pollPaymentStatus('SE-ABC123', fetcher, {
    ...clock,
    signal: controller.signal,
    sleep: async (ms) => { await clock.sleep(ms); controller.abort() },
  })
  assert.equal(out.kind, 'aborted')
  assert.equal(calls.length, 1)
})

// ── generate 402 ─────────────────────────────────────────────────────────────

test('402 from generate shows the server detail and asks for an upgrade', () => {
  const body = JSON.stringify({ detail: 'Plan limit reached (10 stories/month on free). Upgrade to continue.' })
  assert.deepEqual(describeGenerateFailure(402, body), {
    message: 'Plan limit reached (10 stories/month on free). Upgrade to continue.',
    upgrade: true,
  })
  const fallback = describeGenerateFailure(402, 'not json')
  assert.equal(fallback.upgrade, true)
  assert.match(fallback.message, /Upgrade to continue/)
})

test('other generate errors keep the HTTP status text', () => {
  assert.deepEqual(describeGenerateFailure(500, 'Internal Server Error'), {
    message: 'HTTP 500: Internal Server Error',
    upgrade: false,
  })
})

// ── return pages ─────────────────────────────────────────────────────────────

test('tran_id is read from the return URL only when it looks like ours', () => {
  assert.equal(readTranId('?tran_id=SE-0123ABCD'), 'SE-0123ABCD')
  assert.equal(readTranId('?tran_id=<script>'), null)
  assert.equal(readTranId(''), null)
})

test('pending plan round-trips through storage', () => {
  const store = memoryStore()
  savePendingPlan('enterprise', store)
  assert.equal(readPendingPlan(store), 'enterprise')
  clearPendingPlan(store)
  assert.equal(readPendingPlan(store), null)
})

test('pending plan tolerates storage that throws', () => {
  const broken = {
    getItem: () => { throw new Error('blocked') },
    setItem: () => { throw new Error('blocked') },
    removeItem: () => { throw new Error('blocked') },
  }
  savePendingPlan('pro', broken)
  assert.equal(readPendingPlan(broken), null)
  clearPendingPlan(broken)
  assert.equal(readPendingPlan(null), null)
})
