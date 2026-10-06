import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { login } from '../api/endpoints'
import { useAppInfo } from '../app/appearance'
import { LockKeyhole } from 'lucide-react'

export function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const app = useAppInfo()

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      queryClient.setQueryData(['me'], await login(username, password))
      navigate('/chat', { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? 'Your account has no access to the assistant. Ask your administrator for a role.'
          : 'Sign-in failed. Check your username and password.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <form
        className="grid w-full max-w-sm gap-3.5 rounded-2xl border border-line bg-surface p-7 shadow-sm"
        onSubmit={submit}
      >
        <span className="flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
          <LockKeyhole aria-hidden className="size-5" />
        </span>
        <h1 className="text-xl font-semibold">{app.name}</h1>
        <p className="-mt-2 text-muted">Sign in with your work account.</p>
        <label className="grid gap-1 text-sm font-medium">
          Username
          <input className="field font-normal" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        <label className="grid gap-1 text-sm font-medium">
          Password
          <input
            className="field font-normal"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
        <button type="submit" className="btn" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
