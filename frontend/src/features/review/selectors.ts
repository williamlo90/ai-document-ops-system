export type DecisionKind = 'correction' | 'approve' | 'reject'

export function canRecordDecision(status: string, workflowStage?: string): boolean {
  return status === 'needs_review' && workflowStage !== 'correction_requested'
}

export function isApprovalBlocked(severity: string): boolean {
  return severity === 'error'
}

export function reviewStatusTone(status: string): 'success' | 'danger' | 'warning' | 'info' {
  return status === 'approved'
    ? 'success'
    : status === 'rejected'
      ? 'danger'
      : status === 'needs_review'
        ? 'warning'
        : 'info'
}

export function reviewStatusText(status: string, stage?: string): string {
  if (['approved', 'rejected', 'exported'].includes(status))
    return status.replace(/\b\w/g, (value) => value.toUpperCase())
  if (stage === 'correction_requested') return 'Correction requested'
  return status.replaceAll('_', ' ').replace(/\b\w/g, (value) => value.toUpperCase())
}
