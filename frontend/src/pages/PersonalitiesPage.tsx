import { useState } from 'react'
import { Trash2, Plus, X } from 'lucide-react'
import { usePersonalities, useCreatePersonality, useDeletePersonality } from '@/hooks/usePersonalities'

export default function PersonalitiesPage() {
  const { data: personalities, isLoading } = usePersonalities()
  const create = useCreatePersonality()
  const remove = useDeletePersonality()
  const [showForm, setShowForm] = useState(false)

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Personalities</h1>
          <p className="text-sm text-slate-500 mt-0.5">Named presets injected into the Writer node</p>
        </div>
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-1.5">
          <Plus size={15} /> New
        </button>
      </div>

      {showForm && (
        <PersonalityForm
          onSave={async (data) => {
            await create.mutateAsync(data)
            setShowForm(false)
          }}
          onCancel={() => setShowForm(false)}
          saving={create.isPending}
        />
      )}

      {isLoading && <div className="text-slate-500 text-sm">Loading…</div>}

      <div className="flex flex-col gap-3">
        {personalities?.map(p => (
          <div key={p.id} className="card flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="font-medium text-slate-100">{p.name}</div>
              <div className="flex flex-wrap gap-2 mt-2">
                {p.voice         && <Tag label={`Voice: ${p.voice}`}         />}
                {p.tone          && <Tag label={`Tone: ${p.tone}`}           />}
                {p.reading_level && <Tag label={`Level: ${p.reading_level}`} />}
                {p.locale        && <Tag label={p.locale} />}
              </div>
              {p.banned_words.length > 0 && (
                <div className="text-xs text-slate-500 mt-1.5">
                  Banned: {p.banned_words.join(', ')}
                </div>
              )}
            </div>
            <button
              onClick={() => remove.mutate(p.id)}
              className="text-slate-500 hover:text-rose-400 transition-colors shrink-0"
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
        {personalities?.length === 0 && !showForm && (
          <div className="text-slate-600 text-sm text-center py-12">
            No personalities yet — create one to customise the story voice.
          </div>
        )}
      </div>
    </div>
  )
}

function Tag({ label }: { label: string }) {
  return (
    <span className="token-badge capitalize">{label}</span>
  )
}

function PersonalityForm({
  onSave, onCancel, saving,
}: {
  onSave: (data: any) => void
  onCancel: () => void
  saving: boolean
}) {
  const [name,         setName]         = useState('')
  const [voice,        setVoice]        = useState('')
  const [tone,         setTone]         = useState('')
  const [readingLevel, setReadingLevel] = useState('')
  const [banned,       setBanned]       = useState('')

  return (
    <div className="card border-sky-800 mb-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-sm">New personality</h3>
        <button onClick={onCancel} className="text-slate-500 hover:text-slate-300"><X size={15} /></button>
      </div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="col-span-2">
          <label className="label">Name *</label>
          <input className="input" placeholder="e.g. The Pirate" value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div>
          <label className="label">Voice / persona</label>
          <input className="input" placeholder="e.g. pirate, professor" value={voice} onChange={e => setVoice(e.target.value)} />
        </div>
        <div>
          <label className="label">Tone</label>
          <input className="input" placeholder="e.g. humorous" value={tone} onChange={e => setTone(e.target.value)} />
        </div>
        <div>
          <label className="label">Reading level</label>
          <input className="input" placeholder="beginner / expert" value={readingLevel} onChange={e => setReadingLevel(e.target.value)} />
        </div>
        <div>
          <label className="label">Banned words (comma-sep)</label>
          <input className="input" placeholder="boring, dull" value={banned} onChange={e => setBanned(e.target.value)} />
        </div>
      </div>
      <button
        disabled={!name.trim() || saving}
        onClick={() => onSave({
          name,
          voice:         voice || undefined,
          tone:          tone || undefined,
          reading_level: readingLevel || undefined,
          banned_words:  banned ? banned.split(',').map(s => s.trim()) : [],
          locale: 'en',
          is_default: false,
        })}
        className="btn-primary text-sm"
      >
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  )
}
