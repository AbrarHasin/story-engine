import { useState } from 'react'
import { Sparkles, ChevronDown } from 'lucide-react'
import { clsx } from 'clsx'
import { usePersonalities } from '@/hooks/usePersonalities'
import type { GenerateRequest } from '@/hooks/useGenerate'

interface Props {
  onSubmit: (req: GenerateRequest) => void
  isRunning: boolean
}

const TONALITIES = ['neutral', 'humorous', 'serious', 'inspirational', 'dramatic', 'sarcastic']
const AUDIENCES  = ['general', 'children', 'experts', 'executives', 'students']
const LENGTHS    = ['short', 'medium', 'long']
const LOCALES    = [
  { value: 'en', label: 'English' },
  { value: 'bn', label: 'বাংলা' },
  { value: 'ar', label: 'العربية' },
]

export default function ConfigPanel({ onSubmit, isRunning }: Props) {
  const { data: personalities } = usePersonalities()

  const [topic,         setTopic]         = useState('')
  const [tonality,      setTonality]      = useState('neutral')
  const [audience,      setAudience]      = useState('general')
  const [length,        setLength]        = useState('medium')
  const [locale,        setLocale]        = useState('en')
  const [personalityId, setPersonalityId] = useState<string>('')
  const [inclLight,     setInclLight]     = useState(true)
  const [inclDark,      setInclDark]      = useState(true)
  const [inclFacts,     setInclFacts]     = useState(true)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!topic.trim()) return
    onSubmit({
      topic: topic.trim(),
      tonality,
      audience,
      length,
      locale,
      personality_id: personalityId || null,
      include_light: inclLight,
      include_dark:  inclDark,
      include_facts: inclFacts,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="card flex flex-col gap-5 sticky top-20">
      <div>
        <h2 className="text-lg font-semibold text-slate-100 mb-1">Story Config</h2>
        <p className="text-sm text-slate-500">Define what to generate</p>
      </div>

      {/* Topic */}
      <div>
        <label className="label">Topic *</label>
        <textarea
          className="input resize-none h-24"
          placeholder="e.g. The rise of AI agents in software development"
          value={topic}
          onChange={e => setTopic(e.target.value)}
          required
        />
      </div>

      {/* Tonality */}
      <div>
        <label className="label">Tonality</label>
        <div className="flex flex-wrap gap-2">
          {TONALITIES.map(t => (
            <button
              key={t}
              type="button"
              onClick={() => setTonality(t)}
              className={clsx(
                'px-3 py-1 rounded-full text-sm border transition-colors capitalize',
                tonality === t
                  ? 'bg-sky-600 border-sky-600 text-white'
                  : 'border-slate-600 text-slate-400 hover:border-slate-400',
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Audience */}
      <div>
        <label className="label">Audience</label>
        <div className="flex flex-wrap gap-2">
          {AUDIENCES.map(a => (
            <button
              key={a}
              type="button"
              onClick={() => setAudience(a)}
              className={clsx(
                'px-3 py-1 rounded-full text-sm border transition-colors capitalize',
                audience === a
                  ? 'bg-violet-600 border-violet-600 text-white'
                  : 'border-slate-600 text-slate-400 hover:border-slate-400',
              )}
            >
              {a}
            </button>
          ))}
        </div>
      </div>

      {/* Length + Locale row */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Length</label>
          <Select value={length} onChange={setLength} options={LENGTHS.map(l => ({ value: l, label: l }))} />
        </div>
        <div>
          <label className="label">Language</label>
          <Select value={locale} onChange={setLocale} options={LOCALES} />
        </div>
      </div>

      {/* Personality */}
      {personalities && personalities.length > 0 && (
        <div>
          <label className="label">Personality preset</label>
          <Select
            value={personalityId}
            onChange={setPersonalityId}
            options={[
              { value: '', label: 'None (default)' },
              ...personalities.map(p => ({ value: p.id, label: p.name })),
            ]}
          />
        </div>
      )}

      {/* Section toggles */}
      <div>
        <label className="label">Include sections</label>
        <div className="flex gap-4">
          <Toggle label="Light side" checked={inclLight} onChange={setInclLight} color="green" />
          <Toggle label="Dark side"  checked={inclDark}  onChange={setInclDark}  color="red" />
          <Toggle label="Facts"      checked={inclFacts} onChange={setInclFacts} color="amber" />
        </div>
      </div>

      <button
        type="submit"
        disabled={isRunning || !topic.trim()}
        className="btn-primary flex items-center justify-center gap-2 mt-1"
      >
        {isRunning ? (
          <>
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Generating…
          </>
        ) : (
          <>
            <Sparkles size={16} />
            Generate Story
          </>
        )}
      </button>
    </form>
  )
}

function Select({
  value, onChange, options,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="input appearance-none pr-8 capitalize"
      >
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
    </div>
  )
}

function Toggle({
  label, checked, onChange, color,
}: {
  label: string; checked: boolean; onChange: (v: boolean) => void; color: string
}) {
  const colors: Record<string, string> = {
    green: 'bg-emerald-600',
    red:   'bg-rose-600',
    amber: 'bg-amber-500',
  }
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={clsx(
        'flex items-center gap-1.5 text-sm px-2.5 py-1 rounded-lg border transition-all',
        checked
          ? `${colors[color]} border-transparent text-white`
          : 'border-slate-600 text-slate-500',
      )}
    >
      <span className={clsx('w-2 h-2 rounded-full', checked ? 'bg-white' : 'bg-slate-600')} />
      {label}
    </button>
  )
}
