import type { LucideIcon } from 'lucide-react'
import { BarChart3, FileOutput, FileText, Gauge, Inbox } from 'lucide-react'
import type { AppRoute, ProductRole } from './types'

export type NavigationItem = {
  label: string
  path: AppRoute
  icon: LucideIcon
  roles: ProductRole[]
  group: 'work' | 'admin'
}

const allRoles: ProductRole[] = ['uploader', 'reviewer', 'administrator']
const reviewers: ProductRole[] = ['reviewer', 'administrator']
const admins: ProductRole[] = ['administrator']

export const navigationItems: NavigationItem[] = [
  { label: 'Inbox', path: '/inbox', icon: Inbox, roles: reviewers, group: 'work' },
  { label: 'Invoices', path: '/invoices', icon: FileText, roles: allRoles, group: 'work' },
  { label: 'Exports', path: '/exports', icon: FileOutput, roles: admins, group: 'work' },
  { label: 'Quality', path: '/admin/quality', icon: BarChart3, roles: admins, group: 'admin' },
  { label: 'Operations', path: '/admin/operations', icon: Gauge, roles: admins, group: 'admin' },
]

export function defaultRoute(role: ProductRole): AppRoute {
  return role === 'uploader' ? '/invoices' : '/inbox'
}

export function canAccessPath(role: ProductRole, path: string): boolean {
  if (path.startsWith('/review/')) return role !== 'uploader'
  if (['/overview', '/review-queue', '/exceptions'].includes(path)) return role !== 'uploader'
  if (['/evaluation', '/system'].includes(path)) return role === 'administrator'
  const item = navigationItems.find(
    (candidate) => path === candidate.path || path.startsWith(`${candidate.path}/`),
  )
  return item ? item.roles.includes(role) : false
}
