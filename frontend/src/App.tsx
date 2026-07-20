import { QueryClientProvider, useMutation, useQuery } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AlertTriangle, LoaderCircle, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { api } from './api/client'
import { AppShell } from './app/AppShell'
import { defaultRoute } from './app/routes'
import { productRole, type SessionInfo } from './app/types'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { InvoicesPage } from './pages/InvoicesPage'
import { ReviewQueuePage } from './pages/ReviewQueuePage'
import { ReviewWorkspacePage } from './pages/ReviewWorkspacePage'
import { ExceptionsPage } from './pages/ExceptionsPage'
import { ExportsPage } from './pages/ExportsPage'
import { EvaluationPage } from './pages/EvaluationPage'
import { Button, ErrorState, LoadingState } from './shared/ui'
import { queryClient } from './queryClient'
import './product.css'

export default function App() {
  return <QueryClientProvider client={queryClient}><BrowserRouter><SessionGate /></BrowserRouter></QueryClientProvider>
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
    mutationFn: () => api<SessionInfo>('/auth/session', { method: 'POST', body: JSON.stringify({ access_token: token }) }),
    onSuccess: () => { setToken(''); setError(''); void queryClient.invalidateQueries({ queryKey: ['auth-session'] }) },
    onError: (cause: Error) => setError(cause.message),
  })
  const logout = useMutation({
    mutationFn: () => api('/auth/session', { method: 'DELETE' }),
    onSuccess: () => { queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth-session' }); queryClient.setQueryData(['auth-session'], null) },
  })
  if (session.isLoading) return <LoadingState label="Loading workspace" />
  if (session.error) return <ErrorState message={session.error.message} retry={() => void session.refetch()} />
  if (!session.data?.authenticated) return <Login token={token} setToken={setToken} error={error} pending={login.isPending} submit={() => login.mutate()} />

  const role = productRole(session.data)
  return <Routes>
    <Route element={<AppShell session={session.data} signOut={() => logout.mutate()} signingOut={logout.isPending} />}>
      <Route index element={<Navigate to={defaultRoute(role)} replace />} />
      <Route path="overview" element={<PlaceholderPage title="Overview" description="Monitor invoice work that needs attention." />} />
      <Route path="invoices" element={<InvoicesPage />} />
      <Route path="review-queue" element={<ReviewQueuePage />} />
      <Route path="review/:documentId" element={<ReviewWorkspacePage />} />
      <Route path="exceptions" element={<ExceptionsPage />} />
      <Route path="exports" element={<ExportsPage />} />
      <Route path="evaluation" element={<EvaluationPage />} />
      <Route path="system" element={<PlaceholderPage title="System" description="Monitor invoice processing and connected services." />} />
      <Route path="settings" element={<PlaceholderPage title="Settings" description="Manage supported workspace preferences." />} />
    </Route>
    <Route path="*" element={<Navigate to={defaultRoute(role)} replace />} />
  </Routes>
}

function Login({ token, setToken, error, pending, submit }: { token: string; setToken: (value: string) => void; error: string; pending: boolean; submit: () => void }) {
  return <main className="ops-login"><section className="ops-login-card"><span className="ops-login-mark"><ShieldCheck size={24} /></span><h1>Sign in securely</h1><p>Use your workspace access token to continue.</p><label><span>Access token</span><input type="password" autoComplete="current-password" value={token} onChange={(event) => setToken(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && token) submit() }} /></label><Button variant="primary" disabled={!token || pending} onClick={submit}>{pending ? <LoaderCircle className="spin" size={17} /> : <ShieldCheck size={17} />} Sign in</Button>{error ? <div className="ops-login-error"><AlertTriangle size={16} />{error}</div> : null}</section></main>
}
