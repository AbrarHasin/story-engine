import { useQuery, useMutation } from '@tanstack/react-query'
import { apiFetch } from '@/lib/auth'
import { fetchMe, fetchPlans, savePendingPlan, startCheckout, type PaidPlanId } from '@/lib/billing'

/** Current user: plan, plan_limit and stories used this month (all from the server). */
export function useMe(options: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: ['me'],
    queryFn: () => fetchMe(apiFetch),
    refetchInterval: options.refetchInterval ?? false,
  })
}

/** Plan catalogue from GET /api/v1/payment/plans (server settings). */
export function usePlans() {
  return useQuery({
    queryKey: ['plans'],
    queryFn: () => fetchPlans(apiFetch),
    staleTime: 5 * 60 * 1000,
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
