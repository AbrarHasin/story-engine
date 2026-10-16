/**
 * Billing helpers: plan catalogue, quota maths, checkout start and the
 * SSLCommerz return flow.
 *
 * Pure module (no React, no import.meta.env): every network call takes a
 * `fetcher` so the unit tests can pass a mock. The app passes apiFetch.
 *
 * Checkout: POST /api/v1/payment/initiate -> { payment_url } -> the browser
 * goes to the SSLCommerz page. SSLCommerz then sends the browser back to the
 * backend, which redirects to /billing/{success|fail|cancel}?tran_id=...
 * The plan itself is upgraded only by the server-to-server IPN, so the
 * success page waits for /auth/me to report the new plan.
 */

export type PlanId = 'free' | 'pro' | 'enterprise'
export type PaidPlanId = Exclude<PlanId, 'free'>
export type ReturnOutcome = 'success' | 'fail' | 'cancel'

export type Fetcher = (path: string, init?: RequestInit) => Promise<Response>

export interface Plan {
  id: PlanId
  name: string
  priceBdt: number
  /** Completed stories per calendar month (UTC); 0 means unlimited. */
  storiesPerMonth: number
  features: string[]
}

/**
 * Mirrors PLAN_PRICES_BDT (backend/app/models/schemas.py) and the
 * PLAN_LIMIT_* defaults (backend/app/core/config.py). The backend does not
 * expose these yet, so keep them in step by hand.
 */
export const PLANS: readonly Plan[] = [
  {
    id: 'free',
    name: 'Free',
    priceBdt: 0,
    storiesPerMonth: 10,
    features: ['10 stories a month', 'All story personalities', 'Story library'],
  },
  {
    id: 'pro',
    name: 'Pro',
    priceBdt: 499,
    storiesPerMonth: 200,
    features: ['200 stories a month', 'All story personalities', 'Story library'],
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    priceBdt: 1499,
    storiesPerMonth: 0,
    features: ['Unlimited stories', 'All story personalities', 'Story library'],
  },
]

const PLAN_RANK: Record<PlanId, number> = { free: 0, pro: 1, enterprise: 2 }

export function isPlanId(value: unknown): value is PlanId {
  return value === 'free' || value === 'pro' || value === 'enterprise'
}

export function getPlan(id: PlanId): Plan {
  return PLANS.find((p) => p.id === id) ?? PLANS[0]
}

/** True when moving from `current` to `target` is a paid upgrade. */
export function canUpgrade(current: PlanId, target: PlanId): target is PaidPlanId {
  return target !== 'free' && PLAN_RANK[target] > PLAN_RANK[current]
}

export function formatBdt(amount: number): string {
  if (amount === 0) return 'Free'
  return `BDT ${amount.toLocaleString('en-US')}`
}

// ── Current user (GET /api/v1/auth/me) ───────────────────────────────────────

export interface Me {
  id: string
  email: string
  name: string | null
  plan: PlanId
  stories_this_month: number
  total_tokens_used: number
  created_at: string
}

export async function fetchMe(fetcher: Fetcher): Promise<Me> {
  const resp = await fetcher('/api/v1/auth/me')
  if (!resp.ok) throw new Error(await errorDetail(resp))
  const data = await resp.json()
  if (!isPlanId(data?.plan)) throw new Error('Unexpected plan in profile')
  return data as Me
}

export interface QuotaSummary {
  used: number
  limit: number
  unlimited: boolean
  remaining: number | null
  /** 0-100, for the progress bar. */
  percent: number
}

export function quotaSummary(plan: PlanId, storiesThisMonth: number): QuotaSummary {
  const limit = getPlan(plan).storiesPerMonth
  const used = Math.max(0, storiesThisMonth || 0)
  if (limit === 0) return { used, limit, unlimited: true, remaining: null, percent: 0 }
  return {
    used,
    limit,
    unlimited: false,
    remaining: Math.max(0, limit - used),
    percent: Math.min(100, Math.round((used / limit) * 100)),
  }
}

// ── Checkout (POST /api/v1/payment/initiate) ─────────────────────────────────

export interface CheckoutSession {
  payment_url: string
  tran_id: string
  amount: number
  currency: string
}

/** Start an SSLCommerz session; returns the gateway page to send the browser to. */
export async function startCheckout(plan: PaidPlanId, fetcher: Fetcher): Promise<CheckoutSession> {
  let resp: Response
  try {
    resp = await fetcher('/api/v1/payment/initiate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan }),
    })
  } catch {
    throw new Error('Could not reach the server')
  }
  if (!resp.ok) throw new Error(await errorDetail(resp))
  const data = (await resp.json()) as CheckoutSession
  if (!isSafeGatewayUrl(data?.payment_url)) throw new Error('The payment gateway returned an invalid link')
  return data
}

/** Only ever send the browser to an https gateway page. */
export function isSafeGatewayUrl(url: unknown): url is string {
  if (typeof url !== 'string') return false
  try {
    return new URL(url).protocol === 'https:'
  } catch {
    return false
  }
}

/** Readable message from a FastAPI error response. */
export async function errorDetail(resp: Response): Promise<string> {
  let detail = `HTTP ${resp.status}`
  try {
    const data = await resp.json()
    if (typeof data?.detail === 'string') detail = data.detail
    else if (Array.isArray(data?.detail) && data.detail[0]?.msg) detail = data.detail[0].msg
  } catch {
    // keep the status text
  }
  return detail
}

// ── Return pages ─────────────────────────────────────────────────────────────

/** tran_id from the return URL query, only if it looks like ours (SE-...). */
export function readTranId(search: string): string | null {
  const value = new URLSearchParams(search).get('tran_id')
  return value && /^SE-[A-Z0-9]{1,32}$/.test(value) ? value : null
}

/** What the success page should say, given the plan bought and the plan /auth/me reports. */
export function confirmationState(
  pending: PlanId | null,
  current: PlanId | undefined,
  timedOut: boolean,
): 'active' | 'waiting' | 'delayed' | 'unknown' {
  if (!pending) return 'unknown'
  if (current && PLAN_RANK[current] >= PLAN_RANK[pending]) return 'active'
  return timedOut ? 'delayed' : 'waiting'
}

// The plan being bought survives the round trip to SSLCommerz in sessionStorage.
// Storage can throw (private mode, blocked site data); the pages still work without it.
const PENDING_KEY = 'story-engine.pending_plan'

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function sessionStore(): StorageLike | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage
  } catch {
    return null
  }
}

export function savePendingPlan(plan: PaidPlanId, store: StorageLike | null = sessionStore()): void {
  try {
    store?.setItem(PENDING_KEY, plan)
  } catch {
    // ignore
  }
}

export function readPendingPlan(store: StorageLike | null = sessionStore()): PlanId | null {
  try {
    const value = store?.getItem(PENDING_KEY)
    return isPlanId(value) ? value : null
  } catch {
    return null
  }
}

export function clearPendingPlan(store: StorageLike | null = sessionStore()): void {
  try {
    store?.removeItem(PENDING_KEY)
  } catch {
    // ignore
  }
}
