import { ExternalLink, CheckCircle2, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'
import { Link } from 'react-router-dom'
import type { GenerationState, NodeName } from '@/stores/generationStore'
import type { GenerateRequest } from '@/hooks/useGenerate'
import { normalizeBullets } from '@/lib/bullets'

interface Props {
  status: GenerationState['status']
  genState: Omit<GenerationState, 'status' | 'start' | 'nodeComplete' | 'finish' | 'setError' | 'reset'>
  request: GenerateRequest | null
}

const NODE_CONFIG: {
  key: NodeName
  label: string
  color: string
  bg: string
  border: string
  includedBy: keyof GenerateRequest
}[] = [
  { key: 'light_side', label: '☀️ Light Side',    color: 'text-emerald-400', bg: 'bg-emerald-950/40', border: 'border-emerald-800', includedBy: 'include_light' },
  { key: 'dark_side',  label: '🌑 Dark Side',     color: 'text-rose-400',    bg: 'bg-rose-950/40',    border: 'border-rose-800',    includedBy: 'include_dark'  },
  { key: 'facts',      label: '⚡ Interesting Facts', color: 'text-amber-400', bg: 'bg-amber-950/40', border: 'border-amber-800',  includedBy: 'include_facts' },
]

export default function GenerationView({ status, genState, request }: Props) {
  const { completedNodes, nodeResults, tokens, traceUrl, error, errorAction } = genState
  const isRunning = status === 'running'
  const isDone    = status === 'done'

  const storyContent = nodeResults['synthesizer']?.final || nodeResults['writer']?.draft

  return (
    <div className="flex flex-col gap-4">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-slate-100">
            {request?.topic}
          </h2>
          {isRunning && (
            <span className="flex items-center gap-1.5 text-xs text-sky-400">
              <Loader2 size={12} className="animate-spin" />
              Generating
            </span>
          )}
          {isDone && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <CheckCircle2 size={12} />
              Complete
            </span>
          )}
        </div>

        {/* Token usage */}
        <div className="flex items-center gap-2">
          {tokens.input > 0 && (
            <span className="token-badge">
              {tokens.input.toLocaleString()} in / {tokens.output.toLocaleString()} out
            </span>
          )}
          {tokens.cost_usd > 0 && (
            <span className="token-badge text-sky-400">
              ${tokens.cost_usd.toFixed(4)}
            </span>
          )}
          {traceUrl && (
            <a
              href={traceUrl}
              target="_blank"
              rel="noreferrer"
              className="token-badge hover:border-sky-500 hover:text-sky-400 transition-colors flex items-center gap-1"
            >
              <ExternalLink size={10} />
              Trace
            </a>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="card border-rose-700 bg-rose-950/40 text-rose-300 text-sm" role="alert">
          ⚠ {error}
          {errorAction === 'upgrade' && (
            <>
              {' '}
              <Link to="/billing" className="font-medium underline hover:text-rose-200" data-testid="upgrade-link">
                See plans and upgrade
              </Link>
            </>
          )}
        </div>
      )}

      {/* Sub-agent panels — 3 col grid */}
      {request && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {NODE_CONFIG.map(({ key, label, color, bg, border, includedBy }) => {
            if (!request[includedBy]) return null
            const result  = nodeResults[key]
            const done    = completedNodes.has(key)
            const running = isRunning && !done

            return (
              <div key={key} className={clsx('streaming-panel', bg, `border ${border}`)}>
                <div className={clsx('flex items-center gap-2 text-sm font-semibold mb-3', color)}>
                  {running && <Loader2 size={12} className="animate-spin" />}
                  {done    && <CheckCircle2 size={12} />}
                  {label}
                </div>
                {done && result?.bullets ? (
                  <ul className="space-y-1.5">
                    {normalizeBullets(result.bullets).map((b, i) => (
                      <li key={i} className="text-sm text-slate-300 flex gap-2">
                        <span className={clsx('mt-1 shrink-0 w-1.5 h-1.5 rounded-full', color.replace('text-', 'bg-'))} />
                        {b}
                      </li>
                    ))}
                  </ul>
                ) : running ? (
                  <div className="text-sm text-slate-500 streaming-cursor">Researching</div>
                ) : (
                  <div className="text-sm text-slate-600">Waiting…</div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Research node (inline, smaller) */}
      {(completedNodes.has('research') || (isRunning && !completedNodes.has('research'))) && (
        <div className="card bg-slate-800/50 border-slate-700">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 mb-2">
            {completedNodes.has('research')
              ? <CheckCircle2 size={11} />
              : <Loader2 size={11} className="animate-spin" />}
            Research context
          </div>
          {nodeResults['research']?.bullets ? (
            <div className="flex flex-wrap gap-2">
              {normalizeBullets(nodeResults['research'].bullets).map((b, i) => (
                <span key={i} className="token-badge text-slate-300">{b}</span>
              ))}
            </div>
          ) : (
            <div className="text-xs text-slate-600 streaming-cursor">Gathering context</div>
          )}
        </div>
      )}

      {/* Writer panel */}
      {(completedNodes.has('writer') || completedNodes.has('synthesizer') || (isRunning && completedNodes.has('facts'))) && (
        <div className="card border-sky-800 bg-sky-950/20">
          <div className="flex items-center gap-2 text-sm font-semibold text-sky-400 mb-3">
            {completedNodes.has('synthesizer')
              ? <CheckCircle2 size={13} />
              : <Loader2 size={13} className="animate-spin" />}
            {completedNodes.has('synthesizer') ? 'Final Story' : 'Writing…'}
          </div>
          {storyContent ? (
            <div className="prose prose-invert prose-sm max-w-none">
              <pre className="whitespace-pre-wrap font-sans text-slate-200 text-sm leading-relaxed">
                {storyContent}
              </pre>
            </div>
          ) : (
            <div className="text-sm text-slate-500 streaming-cursor">Composing narrative</div>
          )}
        </div>
      )}
    </div>
  )
}
