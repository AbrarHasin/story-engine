import { create } from 'zustand'

export type NodeName = 'research' | 'light_side' | 'dark_side' | 'facts' | 'writer' | 'synthesizer'

export interface NodeResult {
  node: NodeName
  bullets?: string[]
  draft?: string
  final?: string
}

export interface TokenUsage {
  input: number
  output: number
  cost_usd: number
}

export interface GenerationState {
  status: 'idle' | 'running' | 'done' | 'error'
  storyId: string | null
  runId: string | null
  traceUrl: string | null
  completedNodes: Set<NodeName>
  nodeResults: Record<string, NodeResult>
  tokens: TokenUsage
  error: string | null
  /** 'upgrade' when the error is the monthly plan limit (HTTP 402): the UI links to /billing. */
  errorAction: 'upgrade' | null

  // Actions
  start: (storyId: string, runId: string) => void
  nodeComplete: (result: NodeResult & { tokens: TokenUsage }) => void
  finish: (tokens: TokenUsage, traceUrl: string) => void
  setError: (msg: string, action?: 'upgrade' | null) => void
  reset: () => void
}

const initial = {
  status: 'idle' as const,
  storyId: null,
  runId: null,
  traceUrl: null,
  completedNodes: new Set<NodeName>(),
  nodeResults: {},
  tokens: { input: 0, output: 0, cost_usd: 0 },
  error: null,
  errorAction: null,
}

export const useGenerationStore = create<GenerationState>((set) => ({
  ...initial,

  start: (storyId, runId) =>
    set({ ...initial, status: 'running', storyId, runId }),

  nodeComplete: ({ tokens, ...result }) =>
    set((s) => ({
      completedNodes: new Set([...s.completedNodes, result.node]),
      nodeResults: { ...s.nodeResults, [result.node]: result },
      tokens,
    })),

  finish: (tokens, traceUrl) =>
    set({ status: 'done', tokens, traceUrl }),

  setError: (error, action = null) =>
    set({ status: 'error', error, errorAction: action }),

  reset: () => set(initial),
}))
