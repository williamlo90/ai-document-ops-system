import { QueryClientProvider, useMutation, useQuery } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router'
import { AlertTriangle, LoaderCircle, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { api } from './api/client'
import { AppShell } from './app/AppShell'
import { defaultRoute } from './app/routes'
import { productRole, type SessionInfo } from './app/types'
import { InvoicesPage } from './pages/InvoicesPage'
import { InboxPage } from './pages/InboxPage'
import { ReviewWorkspacePage } from './pages/ReviewWorkspacePage'
import { ExportsPage } from './pages/ExportsPage'
import { EvaluationPage } from './pages/EvaluationPage'
import { SystemPage } from './pages/SystemPage'
import { Button, ErrorState, LoadingState } from './shared/ui'
import { queryClient } from './queryClient'
import './styles/index.css'

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionGate />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function SessionGate() {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const session = useQuery({
    queryKey: ['auth-session'],
    queryFn: async () => {
      const response = await fetch('/auth/session', { credentials: 'same-origin' })
      if (response.status === 401) return null
      if (!response.ok) throw new Error('Unable to verify the secure session.')
      return response.json() as Promise<SessionInfo>
    },
    retry: false,
  })
  const login = useMutation({
    mutationFn: () =>
      api<SessionInfo>('/auth/session', {
        method: 'POST',
        body: JSON.stringify({ access_token: token }),
      }),
    onSuccess: () => {
      setToken('')
      setError('')
      void queryClient.invalidateQueries({ queryKey: ['auth-session'] })
    },
    onError: (cause: Error) => setError(cause.message),
  })
  const logout = useMutation({
    mutationFn: () => api('/auth/session', { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth-session' })
      queryClient.setQueryData(['auth-session'], null)
    },
  })
  if (session.isLoading) return <LoadingState label="Loading workspace" />
  if (session.error)
    return <ErrorState message={session.error.message} retry={() => void session.refetch()} />
  if (!session.data?.authenticated)
    return (
      <Login
        token={token}
        setToken={setToken}
        error={error}
        pending={login.isPending}
        submit={() => login.mutate()}
      />
    )

  const role = productRole(session.data)
  return (
    <Routes>
      <Route
        element={
          <AppShell
            session={session.data}
            signOut={() => logout.mutate()}
            signingOut={logout.isPending}
          />
        }
      >
        <Route index element={<Navigate to={defaultRoute(role)} replace />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="invoices" element={<InvoicesPage />} />
        <Route path="review/:documentId" element={<ReviewWorkspacePage />} />
        <Route path="exports" element={<ExportsPage />} />
        <Route path="admin/quality" element={<EvaluationPage />} />
        <Route path="admin/operations" element={<SystemPage />} />
        <Route path="overview" element={<LegacyRedirect to="/inbox" />} />
        <Route
          path="review-queue"
          element={<LegacyRedirect to="/inbox" state="needs-decision" />}
        />
        <Route path="exceptions" element={<LegacyRedirect to="/inbox" state="blocked" />} />
        <Route path="evaluation" element={<LegacyRedirect to="/admin/quality" />} />
        <Route path="system" element={<LegacyRedirect to="/admin/operations" />} />
      </Route>
      <Route path="*" element={<Navigate to={defaultRoute(role)} replace />} />
    </Routes>
  )
}

function LegacyRedirect({ to, state }: { to: string; state?: string }) {
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  if (state) params.set('state', state)
  const query = params.toString()
  return <Navigate to={`${to}${query ? `?${query}` : ''}`} replace />
}

function Login({
  token,
  setToken,
  error,
  pending,
  submit,
}: {
  token: string
  setToken: (value: string) => void
  error: string
  pending: boolean
  submit: () => void
}) {
  return (
    <main className="ops-login">
      <section className="ops-login-card">
        <span className="ops-login-mark">
          <ShieldCheck size={24} />
        </span>
        <span className="ops-login-context">Local demo</span>
        <h1>Open demo workspace</h1>
        <p>Enter a local role token. This demo does not use production identity management.</p>
        <label>
          <span>Role token</span>
          <input
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && token) submit()
            }}
          />
        </label>
        <Button variant="primary" disabled={!token || pending} onClick={submit}>
          {pending ? <LoaderCircle className="spin" size={17} /> : <ShieldCheck size={17} />} Open
          workspace
        </Button>
        {error ? (
          <div className="ops-login-error">
            <AlertTriangle size={16} />
            {error}
          </div>
        ) : null}
      </section>
    </main>
  )
}
