export type SessionInfo = {
  authenticated: boolean
  actor: string
  user_id: string
  workspace_id: string
  role: string
  is_admin: boolean
}

export type ProductRole = 'uploader' | 'reviewer' | 'administrator'

export type WorkspaceSummary = {
  workspace_id: string
  work_items: Array<Record<string, unknown>>
  pending_approvals: Array<Record<string, unknown>>
  documents: Array<Record<string, unknown>>
  metrics: Record<string, number>
}

export type AppRoute =
  | '/overview'
  | '/invoices'
  | '/review-queue'
  | '/exceptions'
  | '/exports'
  | '/evaluation'
  | '/system'
  | '/settings'

export function productRole(session: SessionInfo): ProductRole {
  if (session.is_admin) return 'administrator'
  if (['uploader', 'operator', 'intake'].includes(session.role.toLowerCase())) return 'uploader'
  return 'reviewer'
}
