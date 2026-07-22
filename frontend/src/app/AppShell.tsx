import { useEffect, useMemo, useState } from 'react'
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { FileCheck2, LogOut, Menu, Search, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { canAccessPath, defaultRoute, navigationItems } from './routes'
import { productRole, type SessionInfo, type WorkspaceSummary } from './types'
import type { ShellContext } from './shell-context'

export function AppShell({ session, signOut, signingOut }: { session: SessionInfo; signOut: () => void; signingOut: boolean }) {
  const role = productRole(session)
  const location = useLocation()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [search, setSearch] = useState('')
  const workspace = useQuery({
    queryKey: ['workspace'],
    queryFn: () => api<WorkspaceSummary>('/backoffice/workspace'),
    refetchInterval: 15_000,
  })
  const items = useMemo(() => navigationItems.filter((item) => item.roles.includes(role)), [role])

  useEffect(() => setMobileOpen(false), [location.pathname])
  useEffect(() => {
    document.documentElement.scrollTop = 0
    document.body.scrollTop = 0
  }, [location.pathname])

  if (!canAccessPath(role, location.pathname)) return <Navigate to={defaultRoute(role)} replace />

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault()
    const query = search.trim()
    navigate(query ? `/invoices?search=${encodeURIComponent(query)}` : '/invoices')
  }

  return <div className="ops-app">
    {mobileOpen ? <button className="ops-sidebar-backdrop" aria-label="Dismiss navigation" onClick={() => setMobileOpen(false)} /> : null}
    <aside className={`ops-sidebar ${mobileOpen ? 'is-open' : ''}`}>
      <div className="ops-brand"><span><FileCheck2 size={25} /></span><div><strong>Invoice Review</strong><small>Demo workspace</small></div><button type="button" className="ops-icon-button ops-mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={20} /></button></div>
      <nav aria-label="Primary navigation">
        <span className="ops-nav-label">Invoice work</span>
        {items.filter((item) => item.group === 'work').map((item) => <NavItem key={item.path} {...item} />)}
        {items.some((item) => item.group === 'system') ? <span className="ops-nav-divider" /> : null}
        {items.filter((item) => item.group === 'system').map((item) => <NavItem key={item.path} {...item} />)}
      </nav>
    </aside>
    <div className="ops-workspace">
      <header className="ops-topbar">
        <button type="button" className="ops-icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={22} /></button>
        <form className="ops-global-search" role="search" onSubmit={submitSearch}><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search invoices, vendors, or invoice numbers" placeholder="Search invoices or vendors" /></form>
        <div className="ops-topbar-actions">
          <span className="ops-demo-label">Demo workspace</span>
          <span className="ops-avatar" aria-hidden="true">{initials(session.actor)}</span>
          <span className="ops-account-name">{session.actor}</span>
          <button type="button" className="ops-icon-button" onClick={signOut} disabled={signingOut} aria-label="Sign out"><LogOut size={18} /></button>
        </div>
      </header>
      <main className="ops-main"><Outlet context={{ session, role, workspace: workspace.data, refreshWorkspace: () => void workspace.refetch() } satisfies ShellContext} /></main>
    </div>
  </div>
}

function NavItem({ label, path, icon: Icon }: (typeof navigationItems)[number]) {
  return <NavLink to={path} aria-label={label} className={({ isActive }) => `ops-nav-item ${isActive ? 'is-active' : ''}`}><Icon size={19} /><span>{label}</span></NavLink>
}

function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean)
  return (parts.length > 1 ? `${parts[0][0]}${parts.at(-1)?.[0]}` : value.slice(0, 2)).toUpperCase()
}
