/**
 * Billing helpers: plan catalogue, quota display, checkout start, the
 * SSLCommerz return flow and the "plan limit reached" generate error.
 *
 * Pure module (no React, no import.meta.env): every network call takes a
 * `fetcher` so the unit tests can pass a mock. The app passes apiFetch.
 *
 * Plans come from GET /api/v1/payment/plans (server settings), never from a
 * hard-coded table. Quota comes from GET /api/v1/auth/me (stories_this_month
 * is already reset by the server at the start of a month; plan_limit 0 means
 * unlimited), so the client does no month maths of its own.
 *
 * Checkout: POST /api/v1/payment/initiate -> { payment_url } -> the browser
 * goes to the SSLCommerz page. SSLCommerz then sends the browser back to the
 * backend, which redirects to /billing/{success|fail|cancel}?tran_id=...
 * The plan itself is upgraded only by the server-to-server IPN, so the
 * success page polls GET /api/v1/payment/status/{tran_id} until it settles.
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

const PLAN_RANK: Record<PlanId, number> = { free: 0, pro: 1, enterprise: 2 }

/** Display names for when the plan list has not loaded (or failed to). */
const PLAN_NAMES: Record<PlanId, string> = { free: 'Free', pro: 'Pro', enterprise: 'Enterprise' }

export function isPlanId(value: unknown): value is PlanId {
  return value === 'free' || value === 'pro' || value === 'enterprise'
}

/** Name of a plan, from the loaded catalogue when there is one. */
export function planName(id: PlanId, plans?: readonly Plan[]): string {
  return plans?.find((p) => p.id === id)?.name ?? PLAN_NAMES[id]
}

/** True when moving from `current` to `target` is a paid upgrade. */
export function canUpgrade(current: PlanId, target: PlanId): target is PaidPlanId {
  return target !== 'free' && PLAN_RANK[target] > PLAN_RANK[current]
}

export function formatBdt(amount: number): string {
  if (amount === 0) return 'Free'
  return `BDT ${amount.toLocaleString('en-US')}`
}

/** Feature bullets for a plan card, built from its monthly story allowance. */
export function planFeatures(storiesPerMonth: number): string[] {
  const allowance =
    storiesPerMonth === 0
      ? 'Unlimited stories'
      : `${storiesPerMonth.toLocaleString('en-US')} ${storiesPerMonth === 1 ? 'story' : 'stories'} a month`
  return [allowance, 'All story personalities', 'Story library']
}

// ── Plan catalogue (GET /api/v1/payment/plans, no auth) ──────────────────────

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

/**
 * Turn the /payment/plans body into display plans, sorted free -> enterprise.
 * Unknown plan ids and malformed rows are skipped; no usable row is an error.
 */
export function parsePlans(data: unknown): Plan[] {
  const rows = (data as { plans?: unknown })?.plans
  if (!Array.isArray(rows)) throw new Error('Unexpected plan list from the server')
  const plans: Plan[] = []
  for (const row of rows) {
    const id = row?.id
    if (!isPlanId(id) || !isCount(row?.price_bdt) || !isCount(row?.stories_per_month)) continue
    if (plans.some((p) => p.id === id)) continue
    const storiesPerMonth = Math.floor(row.stories_per_month)
    plans.push({
      id,
      name: typeof row.name === 'string' && row.name.trim() ? row.name : PLAN_NAMES[id],
      priceBdt: row.price_bdt,
      storiesPerMonth,
      features: planFeatures(storiesPerMonth),
    })
  }
  if (plans.length === 0) throw new Error('The server returned no plans')
  return plans.sort((a, b) => PLAN_RANK[a.id] - PLAN_RANK[b.id])
}

export async function fetchPlans(fetcher: Fetcher): Promise<Plan[]> {
  let resp: Response
  try {
    resp = await fetcher('/api/v1/payment/plans')
  } catch {
    throw new Error('Could not reach the server')
  }
  if (!resp.ok) throw new Error(await errorDetail(resp))
  return parsePlans(await resp.json())
}

// ── Current user (GET /api/v1/auth/me) ───────────────────────────────────────

export interface Me {
  id: string
  email: string
  name: string | null
  plan: PlanId
  /** Already reset to 0 by the server when a new month started. */
  stories_this_month: number
  /** Monthly story limit for the plan; 0 means unlimited. */
  plan_limit: number
  total_tokens_used: number
  created_at: string
}

export async function fetchMe(fetcher: Fetcher): Promise<Me> {
  const resp = await fetcher('/api/v1/auth/me')
  if (!resp.ok) throw new Error(await errorDetail(resp))
  const data = await resp.json()
  if (!isPlanId(data?.plan)) throw new Error('Unexpected plan in profile')
  if (!isCount(data?.plan_limit)) throw new Error('Unexpected plan limit in profile')
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

/** Quota from the server's numbers: stories_this_month and plan_limit (0 = unlimited). */
export function quotaSummary(storiesThisMonth: number, planLimit: number): QuotaSummary {
  const limit = Math.max(0, planLimit || 0)
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

/** Readable message from a FastAPI error body (already read as text). */
export function detailFromBody(text: string, fallback: string): string {
  try {
    const data = JSON.parse(text)
    if (typeof data?.detail === 'string' && data.detail) return data.detail
    if (Array.isArray(data?.detail) && typeof data.detail[0]?.msg === 'string') return data.detail[0].msg
  } catch {
    // not JSON
  }
  return fallback
}

/** Readable message from a FastAPI error response. */
export async function errorDetail(resp: Response): Promise<string> {
  const text = await resp.text().catch(() => '')
  return detailFromBody(text, `HTTP ${resp.status}`)
}

// ── Payment status (GET /api/v1/payment/status/{tran_id}) ───────────────────

export type PaymentState = 'initiated' | 'confirmed' | 'failed' | 'cancelled'

export interface PaymentStatus {
  tran_id: string
  status: PaymentState
  plan: PaidPlanId
  amount: number
  currency: string
  confirmed_at: string | null
}

/** A non-2xx answer from the status endpoint, with its HTTP status. */
export class PaymentStatusError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'PaymentStatusError'
    this.status = status
  }
}

function isPaymentState(value: unknown): value is PaymentState {
  return value === 'initiated' || value === 'confirmed' || value === 'failed' || value === 'cancelled'
}

export async function fetchPaymentStatus(tranId: string, fetcher: Fetcher): Promise<PaymentStatus> {
  const resp = await fetcher(`/api/v1/payment/status/${encodeURIComponent(tranId)}`)
  if (!resp.ok) throw new PaymentStatusError(resp.status, await errorDetail(resp))
  const data = await resp.json()
  if (!isPaymentState(data?.status)) throw new Error('Unexpected payment status from the server')
  return data as PaymentStatus
}

export type PollOutcome =
  | { kind: 'confirmed' | 'failed' | 'cancelled'; payment: PaymentStatus }
  | { kind: 'timeout'; payment: PaymentStatus | null }
  | { kind: 'not_found' }
  | { kind: 'error'; message: string }
  | { kind: 'aborted' }

export interface PollOptions {
  intervalMs?: number
  timeoutMs?: number
  signal?: AbortSignal
  /** Called with every status read, e.g. to show the plan while still pending. */
  onUpdate?: (payment: PaymentStatus) => void
  /** Injectable for tests. */
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>
  now?: () => number
}

function defaultSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => { clearTimeout(t); resolve() }, { once: true })
  })
}

/**
 * Poll the payment status every `intervalMs` (default 2 s) until it leaves
 * "initiated" or `timeoutMs` (default 60 s) passes. A 404 (unknown or not
 * ours) and auth errors stop at once; network and server errors are retried
 * until the deadline.
 */
export async function pollPaymentStatus(
  tranId: string,
  fetcher: Fetcher,
  options: PollOptions = {},
): Promise<PollOutcome> {
  const intervalMs = options.intervalMs ?? 2000
  const timeoutMs = options.timeoutMs ?? 60000
  const sleep = options.sleep ?? defaultSleep
  const now = options.now ?? Date.now
  const { signal } = options
  const deadline = now() + timeoutMs
  let last: PaymentStatus | null = null

  for (;;) {
    if (signal?.aborted) return { kind: 'aborted' }
    try {
      const payment = await fetchPaymentStatus(tranId, fetcher)
      if (signal?.aborted) return { kind: 'aborted' }
      last = payment
      options.onUpdate?.(payment)
      if (payment.status !== 'initiated') return { kind: payment.status, payment }
    } catch (err) {
      if (err instanceof PaymentStatusError) {
        if (err.status === 404) return { kind: 'not_found' }
        if (err.status === 401 || err.status === 403) return { kind: 'error', message: err.message }
      }
      // network / 5xx / malformed body: try again until the deadline
    }
    if (now() + intervalMs > deadline) return { kind: 'timeout', payment: last }
    await sleep(intervalMs, signal)
  }
}

// ── Generate errors (POST /api/v1/stories/generate) ──────────────────────────

export interface GenerateFailure {
  message: string
  /** True for 402 "plan limit reached": the UI links to /billing. */
  upgrade: boolean
}

/** What to show when the generate request fails before streaming (not 401). */
export function describeGenerateFailure(status: number, bodyText: string): GenerateFailure {
  if (status === 402) {
    return {
      message: detailFromBody(bodyText, 'You have used all the stories in your plan this month. Upgrade to continue.'),
      upgrade: true,
    }
  }
  return { message: `HTTP ${status}: ${bodyText}`, upgrade: false }
}

// ── Return pages ─────────────────────────────────────────────────────────────

/** tran_id from the return URL query, only if it looks like ours (SE-...). */
export function readTranId(search: string): string | null {
  const value = new URLSearchParams(search).get('tran_id')
  return value && /^SE-[A-Z0-9]{1,32}$/.test(value) ? value : null
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
