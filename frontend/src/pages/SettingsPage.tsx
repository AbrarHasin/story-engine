import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, XCircle, ExternalLink, Server, Database, Cpu, Eye } from 'lucide-react'
import { clsx } from 'clsx'

const API = import.meta.env.VITE_API_BASE_URL || ''
const LANGFUSE = import.meta.env.VITE_LANGFUSE_HOST || 'http://localhost:3000'

interface HealthCheck {
  status: string
  version: string
  db: string
  redis: string
  langfuse: string
}

function useHealth() {
  return useQuery<HealthCheck>({
    queryKey: ['health'],
    queryFn: async () => {
      const r = await fetch(`${API}/health`)
      return r.json()
    },
    refetchInterval: 30000, // poll every 30s
  })
}

export default function SettingsPage() {
  const { data: health, isLoading, error } = useHealth()

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">System health, configuration, and links</p>
      </div>

      {/* System Health */}
      <section className="mb-8">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Server size={14} />
          System Health
        </h2>

        {isLoading && <div className="text-slate-500 text-sm">Checking health...</div>}
        {error && (
          <div className="card border-rose-700 bg-rose-950/40 text-rose-300 text-sm">
            Backend unreachable at {API}
          </div>
        )}

        {health && (
          <div className="grid grid-cols-2 gap-3">
            <HealthCard
              label="API Server"
              status={health.status === 'ok' ? 'ok' : 'error'}
              detail={`v${health.version}`}
              icon={<Cpu size={14} />}
            />
            <HealthCard
              label="PostgreSQL"
              status={health.db === 'ok' ? 'ok' : health.db.startsWith('not checked') ? 'warn' : 'error'}
              detail={health.db}
              icon={<Database size={14} />}
            />
            <HealthCard
              label="Redis"
              status={health.redis === 'ok' ? 'ok' : health.redis === 'not used' ? 'warn' : 'error'}
              detail={health.redis}
              icon={<Database size={14} />}
            />
            <HealthCard
              label="Langfuse"
              status={health.langfuse === 'ok' ? 'ok' : ['not configured', 'disabled'].includes(health.langfuse) ? 'warn' : 'error'}
              detail={health.langfuse}
              icon={<Eye size={14} />}
            />
          </div>
        )}
      </section>

      {/* Quick Links */}
      <section className="mb-8">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          Quick Links
        </h2>
        <div className="flex flex-col gap-2">
          <ExternalLinkCard
            label="API Documentation"
            description="Swagger UI — test endpoints interactively"
            url={`${API}/docs`}
          />
          <ExternalLinkCard
            label="Langfuse Dashboard"
            description="Trace viewer — per-node token usage and latency"
            url={LANGFUSE}
          />
          <ExternalLinkCard
            label="ReDoc"
            description="Alternative API documentation view"
            url={`${API}/redoc`}
          />
        </div>
      </section>

      {/* Configuration */}
      <section className="mb-8">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          Configuration
        </h2>
        <div className="card">
          <div className="grid grid-cols-[140px_1fr] gap-y-3 text-sm">
            <span className="text-slate-500">API URL</span>
            <code className="text-slate-300 font-mono text-xs bg-slate-900 px-2 py-0.5 rounded">{API}</code>

            <span className="text-slate-500">Langfuse URL</span>
            <code className="text-slate-300 font-mono text-xs bg-slate-900 px-2 py-0.5 rounded">{LANGFUSE}</code>

            <span className="text-slate-500">Version</span>
            <span className="text-slate-300">{health?.version ?? '—'}</span>
          </div>
        </div>
      </section>

      {/* Architecture */}
      <section>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          Architecture
        </h2>
        <div className="card bg-slate-800/50 text-sm text-slate-400 font-mono leading-relaxed whitespace-pre">{`Supervisor (Haiku)
  |  fan-out
  +-- Research      (Haiku)
  +-- Light Side    (Haiku)
  +-- Dark Side     (Haiku)
  +-- Facts         (Haiku)
  +-- Personality   (pass-through)
  |  fan-in
Writer (Sonnet)
  |
Synthesizer (Sonnet)
  |
SSE Stream -> Frontend`}</div>
      </section>
    </div>
  )
}


function HealthCard({
  label, status, detail, icon,
}: {
  label: string
  status: 'ok' | 'warn' | 'error'
  detail: string
  icon: React.ReactNode
}) {
  const colors = {
    ok:    { border: 'border-emerald-800', bg: 'bg-emerald-950/30', text: 'text-emerald-400', icon: <CheckCircle2 size={12} /> },
    warn:  { border: 'border-amber-800',   bg: 'bg-amber-950/30',   text: 'text-amber-400',   icon: <XCircle size={12} /> },
    error: { border: 'border-rose-800',    bg: 'bg-rose-950/30',    text: 'text-rose-400',    icon: <XCircle size={12} /> },
  }
  const c = colors[status]

  return (
    <div className={clsx('card', c.bg, `border ${c.border}`)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-slate-300">
          {icon}
          {label}
        </div>
        <span className={clsx('flex items-center gap-1 text-xs', c.text)}>
          {c.icon}
          {status === 'ok' ? 'Healthy' : detail}
        </span>
      </div>
    </div>
  )
}


function ExternalLinkCard({
  label, description, url,
}: {
  label: string; description: string; url: string
}) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="card hover:border-slate-500 transition-colors flex items-center justify-between gap-3"
    >
      <div>
        <div className="text-sm font-medium text-slate-200">{label}</div>
        <div className="text-xs text-slate-500">{description}</div>
      </div>
      <ExternalLink size={14} className="text-slate-500 shrink-0" />
    </a>
  )
}
