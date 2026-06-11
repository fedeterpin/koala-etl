import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { t } from '../i18n/es'
import { Spinner } from '../components/ui'

export function LoginPage() {
  const { user, login, initializing } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!initializing && user) {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from || '/dashboard/usuarios'} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email.trim(), password)
      navigate('/dashboard/usuarios', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setError(t.login.invalidCredentials)
      else if (err instanceof ApiError && err.status === 429) setError(t.login.tooManyAttempts)
      else if (err instanceof ApiError && err.status === 422) setError(t.login.invalidCredentials)
      else setError(t.login.genericError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary-900 via-primary-800 to-primary-600 p-4">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-xl">
        <div className="mb-6 text-center">
          <span className="text-4xl" aria-hidden>
            🐨
          </span>
          <h1 className="mt-2 text-xl font-bold text-gray-900">{t.login.title}</h1>
          <p className="mt-1 text-xs text-gray-500">{t.login.subtitle}</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700">
              {t.login.email}
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700">
              {t.login.password}
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
          </div>
          {error && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
          >
            {busy && <Spinner className="h-4 w-4 text-white" />}
            {busy ? t.login.submitting : t.login.submit}
          </button>
        </form>
      </div>
    </div>
  )
}
