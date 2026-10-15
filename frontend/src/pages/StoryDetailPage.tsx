import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download, ExternalLink, CheckCircle2, XCircle, Loader2, Clock } from 'lucide-react'
import { clsx } from 'clsx'

const API = import.meta.env.VITE_API_BASE_URL || ''

interface StoryDetail {
  id: string
  topic: string
  tonality: string
  audience: string
  status: string
  light_side: string | null
  dark_side: string | null
  facts: string | null
  narrative: string | null
  final_output: string | null
  tokens_input: number
  tokens_output: number
  cost_usd: number
  created_at: string
  completed_at: string | null
}

function useStory(id: string) {
  return useQuery<StoryDetail>({
    queryKey: ['story', id],
    queryFn: async () => {
      const r = await fetch(`${API}/api/v1/stories/${id}`)
      if (!r.ok) throw new Error('Failed to fetch story')
      return r.json()
    },
  })
}

const STATUS_MAP: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  completed: { icon: <CheckCircle2 size={14} />, label: 'Completed', color: 'text-emerald-400' },
  failed:    { icon: <XCircle size={14} />,      label: 'Failed',    color: 'text-rose-400'    },
  running:   { icon: <Loader2 size={14} className="animate-spin" />, label: 'Running', color: 'text-sky-400' },
  pending:   { icon: <Clock size={14} />,        label: 'Pending',   color: 'text-slate-500'   },
}

export default function StoryDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: story, isLoading, error } = useStory(id!)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-sky-400" size={24} />
      </div>
    )
  }

  if (error || !story) {
    return (
      <div className="max-w-3xl">
        <Link to="/library" className="btn-ghost flex items-center gap-1.5 mb-4 w-fit">
          <ArrowLeft size={15} /> Back to Library
        </Link>
        <div className="card border-rose-700 bg-rose-950/40 text-rose-300">
          Failed to load story.
        </div>
      </div>
    )
  }

  const status = STATUS_MAP[story.status] ?? STATUS_MAP.pending
  const content = story.final_output || story.narrative

  const handleExport = () => {
    const md = buildMarkdown(story)
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${story.topic.slice(0, 50).replace(/[^a-zA-Z0-9 ]/g, '')}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="max-w-3xl">
      {/* Nav */}
      <Link to="/library" className="btn-ghost flex items-center gap-1.5 mb-4 w-fit">
        <ArrowLeft size={15} /> Back to Library
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{story.topic}</h1>
          <div className="flex flex-wrap items-center gap-2 mt-2 text-sm">
            <span className={clsx('flex items-center gap-1', status.color)}>
              {status.icon} {status.label}
            </span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400 capitalize">{story.tonality}</span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400 capitalize">{story.audience}</span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-500">{new Date(story.created_at).toLocaleString()}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {story.tokens_input > 0 && (
            <span className="token-badge">
              {story.tokens_input.toLocaleString()} in / {story.tokens_output.toLocaleString()} out
            </span>
          )}
          {story.cost_usd > 0 && (
            <span className="token-badge text-sky-400">${story.cost_usd.toFixed(4)}</span>
          )}
          {story.status === 'completed' && (
            <button onClick={handleExport} className="btn-ghost flex items-center gap-1.5 text-sm">
              <Download size={14} /> Export .md
            </button>
          )}
        </div>
      </div>

      {/* Sub-agent sections */}
      {(story.light_side || story.dark_side || story.facts) && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
          {story.light_side && (
            <SectionCard
              title="Light Side"
              emoji="sun"
              content={story.light_side}
              color="emerald"
            />
          )}
          {story.dark_side && (
            <SectionCard
              title="Dark Side"
              emoji="moon"
              content={story.dark_side}
              color="rose"
            />
          )}
          {story.facts && (
            <SectionCard
              title="Interesting Facts"
              emoji="zap"
              content={story.facts}
              color="amber"
            />
          )}
        </div>
      )}

      {/* Main story content */}
      {content && (
        <div className="card border-sky-800 bg-sky-950/20">
          <h3 className="text-sm font-semibold text-sky-400 mb-3 flex items-center gap-2">
            <CheckCircle2 size={13} />
            {story.final_output ? 'Final Story' : 'Draft'}
          </h3>
          <div className="prose prose-invert prose-sm max-w-none">
            <MarkdownContent text={content} />
          </div>
        </div>
      )}

      {story.status === 'failed' && !content && (
        <div className="card border-rose-700 bg-rose-950/40 text-rose-300 text-sm">
          This story generation failed. Try regenerating with adjusted settings.
        </div>
      )}
    </div>
  )
}


function SectionCard({
  title, content, color,
}: {
  title: string; emoji: string; content: string; color: string
}) {
  const bullets = content.split('\n').filter(Boolean)
  const colorClasses: Record<string, { text: string; bg: string; border: string; dot: string }> = {
    emerald: { text: 'text-emerald-400', bg: 'bg-emerald-950/40', border: 'border-emerald-800', dot: 'bg-emerald-400' },
    rose:    { text: 'text-rose-400',    bg: 'bg-rose-950/40',    border: 'border-rose-800',    dot: 'bg-rose-400'    },
    amber:   { text: 'text-amber-400',   bg: 'bg-amber-950/40',   border: 'border-amber-800',   dot: 'bg-amber-400'   },
  }
  const c = colorClasses[color] ?? colorClasses.emerald

  return (
    <div className={clsx('streaming-panel', c.bg, `border ${c.border}`)}>
      <div className={clsx('text-sm font-semibold mb-3', c.text)}>
        {title}
      </div>
      <ul className="space-y-1.5">
        {bullets.map((b, i) => (
          <li key={i} className="text-sm text-slate-300 flex gap-2">
            <span className={clsx('mt-1.5 shrink-0 w-1.5 h-1.5 rounded-full', c.dot)} />
            {b}
          </li>
        ))}
      </ul>
    </div>
  )
}


/** Minimal markdown renderer — handles ##, **, *, - bullets */
function MarkdownContent({ text }: { text: string }) {
  const lines = text.split('\n')
  const elements: React.ReactNode[] = []
  let key = 0

  for (const line of lines) {
    if (line.startsWith('## ')) {
      elements.push(
        <h2 key={key++} className="text-base font-semibold text-slate-100 mt-4 mb-2">
          {line.slice(3)}
        </h2>
      )
    } else if (line.startsWith('# ')) {
      elements.push(
        <h1 key={key++} className="text-lg font-bold text-slate-100 mt-4 mb-2">
          {line.slice(2)}
        </h1>
      )
    } else if (line.match(/^[-*] /)) {
      elements.push(
        <li key={key++} className="text-sm text-slate-300 ml-4 list-disc">
          <InlineMarkdown text={line.slice(2)} />
        </li>
      )
    } else if (line.trim() === '') {
      elements.push(<div key={key++} className="h-2" />)
    } else {
      elements.push(
        <p key={key++} className="text-sm text-slate-200 leading-relaxed">
          <InlineMarkdown text={line} />
        </p>
      )
    }
  }

  return <div>{elements}</div>
}


function InlineMarkdown({ text }: { text: string }) {
  // Handle **bold** and *italic*
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={i} className="text-slate-100 font-semibold">{part.slice(2, -2)}</strong>
        }
        if (part.startsWith('*') && part.endsWith('*')) {
          return <em key={i}>{part.slice(1, -1)}</em>
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}


function buildMarkdown(story: StoryDetail): string {
  const lines: string[] = []
  lines.push(`# ${story.topic}`)
  lines.push('')
  lines.push(`> Tonality: ${story.tonality} | Audience: ${story.audience} | Generated: ${new Date(story.created_at).toLocaleString()}`)
  lines.push('')

  if (story.light_side) {
    lines.push('## Light Side')
    story.light_side.split('\n').filter(Boolean).forEach(b => lines.push(`- ${b}`))
    lines.push('')
  }

  if (story.dark_side) {
    lines.push('## Dark Side')
    story.dark_side.split('\n').filter(Boolean).forEach(b => lines.push(`- ${b}`))
    lines.push('')
  }

  if (story.facts) {
    lines.push('## Interesting Facts')
    story.facts.split('\n').filter(Boolean).forEach(b => lines.push(`- ${b}`))
    lines.push('')
  }

  const content = story.final_output || story.narrative
  if (content) {
    lines.push('## Story')
    lines.push(content)
    lines.push('')
  }

  lines.push('---')
  lines.push(`Tokens: ${story.tokens_input} in / ${story.tokens_output} out | Cost: $${story.cost_usd.toFixed(4)}`)
  lines.push('Generated by Story Engine')

  return lines.join('\n')
}
