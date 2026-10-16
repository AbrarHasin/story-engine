import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '@/lib/auth'
import { fetchMe, savePendingPlan, startCheckout, type PaidPlanId } from '@/lib/billing'

/** Current user: plan + stories used this month. */
export function useMe(options: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: ['me'],
    queryFn: () => fetchMe(apiFetch),
    refetchInterval: options.refetchInterval ?? false,
  })
}

/** Start an SSLCommerz checkout and send the browser to the gateway page. */
export function useCheckout() {
  return useMutation({
    mutationFn: (plan: PaidPlanId) => startCheckout(plan, apiFetch),
    onSuccess: (session, plan) => {
      savePendingPlan(plan)
      window.location.assign(session.payment_url)
    },
  })
}
