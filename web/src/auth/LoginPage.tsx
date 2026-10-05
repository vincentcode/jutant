import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { login } from '../api/endpoints'
import styles from './LoginPage.module.css'

export function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

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
    <main className={styles.page}>
      <form className={styles.form} onSubmit={submit}>
        <h1>Staff Assistant</h1>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <p role="alert" className={styles.error}>
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
