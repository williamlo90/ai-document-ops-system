import type { SystemJob, SystemStatus } from './types'

export const systemTabs = ['status', 'processing', 'integrations', 'audit'] as const

export type SystemTab = (typeof systemTabs)[number]

export function isSystemTab(value: string | null): value is SystemTab {
  return systemTabs.includes(value as SystemTab)
}

export function filterSystemJobs(
  jobs: SystemJob[],
  filter: string | null,
  stage: string | null,
): SystemJob[] {
  return jobs.filter((job) => {
    const filterMatch =
      !filter ||
      (filter === 'active' && job.status === 'running') ||
      (filter === 'waiting' && ['queued', 'retrying'].includes(job.status)) ||
      (filter === 'completed' && job.status === 'succeeded') ||
      (filter === 'attention' && ['failed', 'dead_letter'].includes(job.status))
    return filterMatch && (!stage || stageMatches(stage, job))
  })
}

export function serviceTone(status: SystemStatus): 'success' | 'warning' | 'danger' | 'neutral' {
  return status === 'operational'
    ? 'success'
    : status === 'degraded'
      ? 'warning'
      : status === 'unavailable'
        ? 'danger'
        : 'neutral'
}

export function jobTone(
  status: SystemJob['status'],
): 'success' | 'info' | 'warning' | 'danger' | 'neutral' {
  return status === 'succeeded'
    ? 'success'
    : status === 'running'
      ? 'info'
      : ['queued', 'retrying'].includes(status)
        ? 'warning'
        : ['failed', 'dead_letter'].includes(status)
          ? 'danger'
          : 'neutral'
}

export function formatDuration(value: number | null) {
  if (value == null) return '-'
  if (value < 1000) return `${value}ms`
  const seconds = value / 1000
  return seconds < 60
    ? `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
    : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

function stageMatches(stage: string, job: SystemJob) {
  if (stage === 'upload') return job.status === 'queued'
  if (stage === 'read')
    return ['running', 'succeeded', 'failed', 'dead_letter'].includes(job.status)
  if (['extract', 'checks'].includes(stage)) return job.status === 'succeeded'
  return false
}
