import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { BookOpen, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'
import { authenticate, useAuthStore } from '@/lib/auth'

type Mode = 'login' | 'register'

export default function LoginPage() {
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/'

  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (token) return <Navigate to={from} replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await authenticate(mode, { email, password, name: mode === 'register' ? name : undefined })
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <div className="flex items-center justify-center gap-2 font-bold text-sky-400 text-xl mb-6">
        <BookOpen size={22} />
        Story Engine
      </div>

      <div className="flex mb-4 rounded-lg bg-slate-900 p-1">
        {(['login', 'register'] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => { setMode(m); setError(null) }}
            className={clsx(
              'flex-1 py-1.5 rounded-md text-sm font-medium transition-colors',
              mode === m ? 'bg-sky-900/50 text-sky-400' : 'text-slate-400 hover:text-slate-100',
            )}
          >
            {m === 'login' ? 'Log in' : 'Create account'}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="space-y-3" aria-label={mode === 'login' ? 'Log in' : 'Create account'}>
        {mode === 'register' && (
          <Field label="Name" type="text" value={name} onChange={setName} autoComplete="name" />
        )}
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          minLength={mode === 'register' ? 8 : undefined}
        />

        {error && (
          <p role="alert" className="text-sm text-red-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-60 text-white text-sm font-medium transition-colors"
        >
          {busy && <Loader2 size={15} className="animate-spin" />}
          {mode === 'login' ? 'Log in' : 'Create account'}
        </button>
      </form>
    </div>
  )
}

function Field({
  label, type, value, onChange, autoComplete, minLength,
}: {
  label: string
  type: string
  value: string
  onChange: (v: string) => void
  autoComplete: string
  minLength?: number
}) {
  return (
    <label className="block">
      <span className="block text-xs text-slate-400 mb-1">{label}</span>
      <input
        type={type}
        value={value}
        required
        minLength={minLength}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 text-sm focus:outline-none focus:border-sky-600"
      />
    </label>
  )
}
