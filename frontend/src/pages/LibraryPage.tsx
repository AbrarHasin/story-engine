import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Clock, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'
import { apiFetch } from '@/lib/auth'


interface Story {
  id: string
  topic: string
  tonality: string
  audience: string
  status: string
  tokens_input: number
  tokens_output: number
  cost_usd: number
  created_at: string
  completed_at: string | null
}

function useStories() {
  return useQuery<Story[]>({
    queryKey: ['stories'],
    queryFn: async () => {
      const r = await apiFetch(`/api/v1/stories/`)
      if (!r.ok) throw new Error('Failed to fetch stories')
      return r.json()
    },
  })
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  completed: <CheckCircle2 size={14} className="text-emerald-400" />,
  failed:    <XCircle size={14} className="text-rose-400" />,
  running:   <Loader2 size={14} className="text-sky-400 animate-spin" />,
  pending:   <Clock size={14} className="text-slate-500" />,
}

export default function LibraryPage() {
  const { data: stories, isLoading, error } = useStories()

  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Library</h1>
        <p className="text-sm text-slate-500 mt-0.5">All generated stories</p>
      </div>

      {isLoading && <div className="text-slate-500 text-sm">Loading…</div>}
      {error    && <div className="text-rose-400 text-sm">Failed to load stories</div>}

      <div className="flex flex-col gap-3">
        {stories?.map(story => (
          <Link key={story.id} to={`/stories/${story.id}`} className="block">
            <div className="card hover:border-slate-600 transition-colors cursor-pointer">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {STATUS_ICON[story.status] ?? STATUS_ICON.pending}
                    <span className="font-medium text-slate-100 truncate">{story.topic}</span>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                    <span className="capitalize">{story.tonality}</span>
                    <span>·</span>
                    <span className="capitalize">{story.audience}</span>
                    <span>·</span>
                    <span>{new Date(story.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  {story.cost_usd > 0 && (
                    <div className="token-badge">${story.cost_usd.toFixed(4)}</div>
                  )}
                  {story.tokens_input > 0 && (
                    <div className="text-xs text-slate-600 mt-1">
                      {story.tokens_input.toLocaleString()} tok in
                    </div>
                  )}
                </div>
              </div>
            </div>
          </Link>
        ))}
        {stories?.length === 0 && (
          <div className="text-slate-600 text-sm text-center py-12">
            No stories yet — generate your first one.
          </div>
        )}
      </div>
    </div>
  )
}
