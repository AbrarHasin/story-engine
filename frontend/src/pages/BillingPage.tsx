import { Check, CreditCard, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'
import { useCheckout, useMe } from '@/hooks/useBilling'
import { PLANS, canUpgrade, formatBdt, getPlan, quotaSummary, type Plan, type PlanId } from '@/lib/billing'

export default function BillingPage() {
  const { data: me, isLoading, error } = useMe()
  const checkout = useCheckout()

  return (
    <div className="max-w-4xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Billing</h1>
        <p className="text-sm text-slate-500 mt-0.5">Your plan, this month's usage, and upgrades</p>
      </div>

      {/* Current plan + quota */}
      <section className="mb-8">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3 flex items-center gap-2">
          <CreditCard size={14} />
          Current plan
        </h2>
        {isLoading && <div className="text-slate-500 text-sm">Loading your plan...</div>}
        {error && (
          <div className="card border-rose-700 bg-rose-950/40 text-rose-300 text-sm" role="alert">
            Could not load your plan: {error.message}
          </div>
        )}
        {me && <CurrentPlan plan={me.plan} storiesThisMonth={me.stories_this_month} />}
      </section>

      {/* Plans */}
      <section>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">Plans</h2>
        {checkout.error && (
          <div className="card border-rose-700 bg-rose-950/40 text-rose-300 text-sm mb-3" role="alert">
            Checkout could not start: {checkout.error.message}
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          {PLANS.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              current={me?.plan}
              busy={checkout.isPending && checkout.variables === plan.id}
              disabled={!me || checkout.isPending}
              onUpgrade={() => {
                if (me && canUpgrade(me.plan, plan.id)) checkout.mutate(plan.id)
              }}
            />
          ))}
        </div>
        <p className="text-xs text-slate-500 mt-3">
          Payments go through SSLCommerz. Prices are per month in Bangladeshi Taka. Your plan changes once
          SSLCommerz confirms the payment, usually within a minute.
        </p>
      </section>
    </div>
  )
}

function CurrentPlan({ plan, storiesThisMonth }: { plan: PlanId; storiesThisMonth: number }) {
  const q = quotaSummary(plan, storiesThisMonth)
  return (
    <div className="card">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-lg font-semibold text-slate-100" data-testid="current-plan">
          {getPlan(plan).name}
        </div>
        <div className="text-sm text-slate-400">{formatBdt(getPlan(plan).priceBdt)}{plan !== 'free' && ' / month'}</div>
      </div>
      <div className="mt-4 text-sm text-slate-300" data-testid="quota">
        {q.unlimited
          ? `${q.used} stories this month (unlimited)`
          : `${q.used} of ${q.limit} stories used this month, ${q.remaining} left`}
      </div>
      {!q.unlimited && (
        <div
          className="mt-2 h-2 rounded-full bg-slate-800 overflow-hidden"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={q.limit}
          aria-valuenow={q.used}
        >
          <div
            className={clsx('h-full rounded-full', q.percent >= 90 ? 'bg-rose-500' : 'bg-sky-500')}
            style={{ width: `${q.percent}%` }}
          />
        </div>
      )}
      <div className="mt-2 text-xs text-slate-500">The count resets at the start of each calendar month (UTC).</div>
    </div>
  )
}

function PlanCard({
  plan, current, busy, disabled, onUpgrade,
}: {
  plan: Plan
  current: PlanId | undefined
  busy: boolean
  disabled: boolean
  onUpgrade: () => void
}) {
  const isCurrent = current === plan.id
  const upgradable = current !== undefined && canUpgrade(current, plan.id)

  return (
    <div className={clsx('card flex flex-col', isCurrent && 'border-sky-700')}>
      <div className="font-semibold text-slate-100">{plan.name}</div>
      <div className="text-2xl font-bold text-slate-100 mt-1">
        {formatBdt(plan.priceBdt)}
        {plan.priceBdt > 0 && <span className="text-sm font-normal text-slate-500"> / month</span>}
      </div>
      <ul className="mt-3 flex-1 space-y-1.5 text-sm text-slate-300">
        {plan.features.map((f) => (
          <li key={f} className="flex items-center gap-2">
            <Check size={14} className="text-emerald-400 shrink-0" />
            {f}
          </li>
        ))}
      </ul>
      <div className="mt-4">
        {isCurrent ? (
          <div className="text-sm text-sky-400 font-medium">Your current plan</div>
        ) : upgradable ? (
          <button type="button" className="btn-primary w-full flex items-center justify-center gap-2" disabled={disabled} onClick={onUpgrade}>
            {busy && <Loader2 size={14} className="animate-spin" />}
            {busy ? 'Opening SSLCommerz...' : `Upgrade to ${plan.name}`}
          </button>
        ) : (
          <div className="text-sm text-slate-500">Included in your plan</div>
        )}
      </div>
    </div>
  )
}
