// Unit tests for src/lib/billing.ts with a mocked API. Run: npm run test:unit
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  PLANS, canUpgrade, clearPendingPlan, confirmationState, fetchMe, formatBdt, isSafeGatewayUrl,
  quotaSummary, readPendingPlan, readTranId, savePendingPlan, startCheckout, type Fetcher,
} from '../src/lib/billing.ts'

interface Call { path: string; init?: RequestInit }

function mockApi(status: number, body: unknown): { fetcher: Fetcher; calls: Call[] } {
  const calls: Call[] = []
  const fetcher: Fetcher = async (path, init) => {
    calls.push({ path, init })
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  }
  return { fetcher, calls }
}

function memoryStore() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
  }
}

// ── plans + quota ────────────────────────────────────────────────────────────

test('plan catalogue matches backend prices and default limits', () => {
  assert.deepEqual(
    PLANS.map((p) => [p.id, p.priceBdt, p.storiesPerMonth]),
    [['free', 0, 10], ['pro', 499, 200], ['enterprise', 1499, 0]],
  )
})

test('only higher paid plans are upgrades', () => {
  assert.equal(canUpgrade('free', 'pro'), true)
  assert.equal(canUpgrade('free', 'enterprise'), true)
  assert.equal(canUpgrade('pro', 'enterprise'), true)
  assert.equal(canUpgrade('pro', 'pro'), false)
  assert.equal(canUpgrade('enterprise', 'pro'), false)
  assert.equal(canUpgrade('pro', 'free'), false)
})

test('quota summary for a limited plan', () => {
  assert.deepEqual(quotaSummary('free', 4), { used: 4, limit: 10, unlimited: false, remaining: 6, percent: 40 })
})

test('quota summary clamps at the limit', () => {
  const q = quotaSummary('free', 12)
  assert.equal(q.remaining, 0)
  assert.equal(q.percent, 100)
})

test('enterprise quota is unlimited', () => {
  const q = quotaSummary('enterprise', 999)
  assert.equal(q.unlimited, true)
  assert.equal(q.remaining, null)
})

test('prices format in taka', () => {
  assert.equal(formatBdt(0), 'Free')
  assert.equal(formatBdt(1499), 'BDT 1,499')
})

// ── /auth/me ─────────────────────────────────────────────────────────────────

test('fetchMe reads plan and usage from /api/v1/auth/me', async () => {
  const { fetcher, calls } = mockApi(200, {
    id: 'u1', email: 'a@b.test', name: 'A', plan: 'pro',
    stories_this_month: 3, total_tokens_used: 100, created_at: '2026-10-01T00:00:00Z',
  })
  const me = await fetchMe(fetcher)
  assert.equal(calls[0].path, '/api/v1/auth/me')
  assert.equal(me.plan, 'pro')
  assert.equal(me.stories_this_month, 3)
})

test('fetchMe surfaces the API error detail', async () => {
  const { fetcher } = mockApi(401, { detail: 'Not authenticated' })
  await assert.rejects(fetchMe(fetcher), /Not authenticated/)
})

test('fetchMe rejects an unknown plan', async () => {
  const { fetcher } = mockApi(200, { plan: 'gold' })
  await assert.rejects(fetchMe(fetcher), /Unexpected plan/)
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

// ── return pages ─────────────────────────────────────────────────────────────

test('tran_id is read from the return URL only when it looks like ours', () => {
  assert.equal(readTranId('?tran_id=SE-0123ABCD'), 'SE-0123ABCD')
  assert.equal(readTranId('?tran_id=<script>'), null)
  assert.equal(readTranId(''), null)
})

test('success page state follows the plan /auth/me reports', () => {
  assert.equal(confirmationState('pro', 'free', false), 'waiting')
  assert.equal(confirmationState('pro', 'pro', false), 'active')
  assert.equal(confirmationState('pro', 'enterprise', false), 'active')
  assert.equal(confirmationState('pro', 'free', true), 'delayed')
  assert.equal(confirmationState(null, 'free', false), 'unknown')
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
