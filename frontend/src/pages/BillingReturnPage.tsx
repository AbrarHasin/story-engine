import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Clock, XCircle, Loader2, HelpCircle } from 'lucide-react'
import { apiFetch } from '@/lib/auth'
import {
  clearPendingPlan, planName, pollPaymentStatus, readPendingPlan, readTranId,
  type PaymentStatus, type PlanId, type PollOutcome, type ReturnOutcome,
} from '@/lib/billing'

const POLL_MS = 2000
const WAIT_MS = 60000

/** Where SSLCommerz (via the backend redirect) sends the browser after checkout. */
export default function BillingReturnPage({ outcome }: { outcome: ReturnOutcome }) {
  const tranId = readTranId(useLocation().search)
  const [pending] = useState(readPendingPlan)

  if (outcome === 'success') {
    if (!tranId) {
      return (
        <ReturnCard icon={<HelpCircle size={28} className="text-amber-400" />} title="Payment status unknown" tranId={null}>
          The return link has no transaction ID, so we cannot check this payment. If you paid, your plan changes once
          SSLCommerz confirms it; check the billing page in a few minutes.
        </ReturnCard>
      )
    }
    return <SuccessView key={tranId} tranId={tranId} pending={pending} />
  }

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

/** Polls GET /payment/status/{tran_id} until the payment settles or the wait runs out. */
function SuccessView({ tranId, pending }: { tranId: string; pending: PlanId | null }) {
  const queryClient = useQueryClient()
  const [payment, setPayment] = useState<PaymentStatus | null>(null)
  const [result, setResult] = useState<PollOutcome | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void pollPaymentStatus(tranId, apiFetch, {
      intervalMs: POLL_MS,
      timeoutMs: WAIT_MS,
      signal: controller.signal,
      onUpdate: setPayment,
    }).then((outcome) => {
      if (outcome.kind === 'aborted') return
      setResult(outcome)
      if (outcome.kind === 'confirmed') {
        clearPendingPlan()
        void queryClient.invalidateQueries({ queryKey: ['me'] })
      } else if (outcome.kind === 'failed' || outcome.kind === 'cancelled') {
        clearPendingPlan()
      }
    })
    return () => controller.abort()
  }, [tranId, queryClient])

  const plan = payment?.plan ?? pending
  const name = plan ? planName(plan) : 'your new plan'

  if (!result) {
    return (
      <ReturnCard icon={<Loader2 size={28} className="text-sky-400 animate-spin" />} title="Confirming your payment" tranId={tranId}>
        SSLCommerz accepted the payment. Waiting for it to confirm {name} with us; this usually takes a few seconds.
      </ReturnCard>
    )
  }

  switch (result.kind) {
    case 'confirmed':
      return (
        <ReturnCard icon={<CheckCircle2 size={28} className="text-emerald-400" />} title={`${planName(result.payment.plan)} is active`} tranId={tranId}>
          Payment confirmed. Your new monthly story limit applies now.
        </ReturnCard>
      )
    case 'failed':
    case 'cancelled':
      return (
        <ReturnCard icon={<XCircle size={28} className="text-rose-400" />} title={result.kind === 'failed' ? 'Payment failed' : 'Payment cancelled'} tranId={tranId}>
          {result.kind === 'failed'
            ? 'SSLCommerz reported that the payment did not go through. Your plan is unchanged; you can try again from the billing page.'
            : 'The payment was cancelled. Your plan is unchanged.'}
        </ReturnCard>
      )
    case 'not_found':
      return (
        <ReturnCard icon={<HelpCircle size={28} className="text-amber-400" />} title="Payment not found" tranId={tranId}>
          We have no payment with this transaction ID on your account. If you were charged, contact support with the
          transaction ID.
        </ReturnCard>
      )
    case 'error':
      return (
        <ReturnCard icon={<XCircle size={28} className="text-rose-400" />} title="Could not check the payment" tranId={tranId}>
          {result.message}. Your plan changes once SSLCommerz confirms the payment; check the billing page in a few minutes.
        </ReturnCard>
      )
    default:
      return (
        <ReturnCard icon={<Clock size={28} className="text-amber-400" />} title="Payment received" tranId={tranId}>
          SSLCommerz has not confirmed {name} yet. Your plan changes as soon as it does; check the billing page in a few
          minutes. Keep the transaction ID if you contact support.
        </ReturnCard>
      )
  }
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
