import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { CheckCircle2, Clock, XCircle, Loader2 } from 'lucide-react'
import { useMe } from '@/hooks/useBilling'
import {
  clearPendingPlan, confirmationState, getPlan, readPendingPlan, readTranId, type ReturnOutcome,
} from '@/lib/billing'

const POLL_MS = 3000
const WAIT_MS = 60000

/** Where SSLCommerz (via the backend redirect) sends the browser after checkout. */
export default function BillingReturnPage({ outcome }: { outcome: ReturnOutcome }) {
  const tranId = readTranId(useLocation().search)
  const [pending] = useState(readPendingPlan)

  if (outcome === 'success') return <SuccessView tranId={tranId} pending={pending} />

  return (
    <ReturnCard
      icon={<XCircle size={28} className={outcome === 'fail' ? 'text-rose-400' : 'text-slate-400'} />}
      title={outcome === 'fail' ? 'Payment failed' : 'Payment cancelled'}
      tranId={tranId}
    >
      {outcome === 'fail'
        ? 'SSLCommerz could not complete the payment. Your plan is unchanged; you can try again from the billing page.'
        : 'You cancelled the payment. Your plan is unchanged.'}
    </ReturnCard>
  )
}

function SuccessView({ tranId, pending }: { tranId: string | null; pending: ReturnType<typeof readPendingPlan> }) {
  const [timedOut, setTimedOut] = useState(false)
  const [polling, setPolling] = useState(true)
  const { data: me } = useMe({ refetchInterval: polling ? POLL_MS : false })
  const state = confirmationState(pending, me?.plan, timedOut)

  useEffect(() => {
    const t = window.setTimeout(() => setTimedOut(true), WAIT_MS)
    return () => window.clearTimeout(t)
  }, [])

  useEffect(() => {
    if (state === 'active') clearPendingPlan()
    if (state !== 'waiting') setPolling(false)
  }, [state])

  const planName = pending ? getPlan(pending).name : null

  if (state === 'active') {
    return (
      <ReturnCard icon={<CheckCircle2 size={28} className="text-emerald-400" />} title={`${planName} is active`} tranId={tranId}>
        Payment confirmed. Your new monthly story limit applies now.
      </ReturnCard>
    )
  }
  if (state === 'waiting') {
    return (
      <ReturnCard icon={<Loader2 size={28} className="text-sky-400 animate-spin" />} title="Confirming your payment" tranId={tranId}>
        SSLCommerz accepted the payment. Waiting for it to confirm {planName} with us; this usually takes a few seconds.
      </ReturnCard>
    )
  }
  return (
    <ReturnCard icon={<Clock size={28} className="text-amber-400" />} title="Payment received" tranId={tranId}>
      {state === 'delayed'
        ? `SSLCommerz has not confirmed ${planName} yet. Your plan changes as soon as it does; check the billing page in a few minutes. Keep the transaction ID if you contact support.`
        : 'Your plan changes once SSLCommerz confirms the payment. Check the billing page in a minute.'}
    </ReturnCard>
  )
}

function ReturnCard({
  icon, title, tranId, children,
}: {
  icon: React.ReactNode
  title: string
  tranId: string | null
  children: React.ReactNode
}) {
  return (
    <div className="max-w-lg mx-auto mt-10 card text-center">
      <div className="flex justify-center mb-3">{icon}</div>
      <h1 className="text-lg font-semibold text-slate-100">{title}</h1>
      <p className="text-sm text-slate-400 mt-2">{children}</p>
      {tranId && (
        <p className="text-xs text-slate-500 mt-3">
          Transaction ID: <code className="font-mono">{tranId}</code>
        </p>
      )}
      <Link to="/billing" className="btn-primary inline-block mt-5">
        Back to billing
      </Link>
    </div>
  )
}
