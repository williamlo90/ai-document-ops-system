import type { LucideIcon } from 'lucide-react'
import { BarChart3, FileOutput, FileText, Gauge, House, Settings, TriangleAlert, ClipboardCheck } from 'lucide-react'
import type { AppRoute, ProductRole } from './types'

export type NavigationItem = {
  label: string
  path: AppRoute
  icon: LucideIcon
  roles: ProductRole[]
  group: 'work' | 'system'
}

const allRoles: ProductRole[] = ['uploader', 'reviewer', 'administrator']
const reviewers: ProductRole[] = ['reviewer', 'administrator']
const admins: ProductRole[] = ['administrator']

export const navigationItems: NavigationItem[] = [
  { label: 'Overview', path: '/overview', icon: House, roles: reviewers, group: 'work' },
  { label: 'Invoices', path: '/invoices', icon: FileText, roles: allRoles, group: 'work' },
  { label: 'Review Queue', path: '/review-queue', icon: ClipboardCheck, roles: reviewers, group: 'work' },
  { label: 'Exceptions', path: '/exceptions', icon: TriangleAlert, roles: reviewers, group: 'work' },
  { label: 'Exports', path: '/exports', icon: FileOutput, roles: admins, group: 'work' },
  { label: 'Evaluation', path: '/evaluation', icon: BarChart3, roles: admins, group: 'work' },
  { label: 'System', path: '/system', icon: Gauge, roles: admins, group: 'system' },
  { label: 'Settings', path: '/settings', icon: Settings, roles: admins, group: 'system' },
]

export function defaultRoute(role: ProductRole): AppRoute {
  return role === 'uploader' ? '/invoices' : '/overview'
}

export function canAccessPath(role: ProductRole, path: string): boolean {
  if (path.startsWith('/review/')) return role !== 'uploader'
  const item = navigationItems.find((candidate) => path === candidate.path || path.startsWith(`${candidate.path}/`))
  return item ? item.roles.includes(role) : false
}
