import {
  ChevronRight,
  CloudUpload,
  Database,
  FileCheck2,
  FileSearch,
  FolderLock,
  RotateCcw,
  ServerCog,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatDate, humanize } from '../../invoices/format'
import { StatusBadge } from '../../../shared/ui'
import { formatDuration, jobTone, serviceTone } from '../selectors'
import type { SystemJob, SystemStatus } from '../types'

export function ServiceBadge({ status }: { status: SystemStatus }) {
  return <StatusBadge tone={serviceTone(status)}>{humanize(status)}</StatusBadge>
}

export function JobBadge({ status }: { status: SystemJob['status'] }) {
  return (
    <StatusBadge tone={jobTone(status)}>
      {status === 'succeeded' ? 'Completed' : humanize(status)}
    </StatusBadge>
  )
}

export function ServiceIcon({ id }: { id: string }) {
  const props = { size: 16, 'aria-hidden': true } as const
  if (id === 'uploads') return <CloudUpload {...props} />
  if (id === 'reader') return <FileSearch {...props} />
  if (id === 'extractor') return <Database {...props} />
  if (id === 'storage') return <FolderLock {...props} />
  if (id === 'accounting_export') return <FileCheck2 {...props} />
  return <ServerCog {...props} />
}

export function JobTable({
  jobs,
  open,
  retry,
  pending,
}: {
  jobs: SystemJob[]
  open: (item: SystemJob) => void
  retry?: (item: SystemJob) => void
  pending?: boolean
}) {
  return (
    <div className="ops-table-wrap">
      <table className="ops-table system-job-table">
        <thead>
          <tr>
            <th>Invoice</th>
            <th>Stage</th>
            <th>Status</th>
            <th>Started</th>
            <th>Duration</th>
            <th>Attempts</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>
                <Link className="ops-link" to={`/review/${job.document_id}`}>
                  {job.invoice}
                </Link>
                <small>{job.filename}</small>
              </td>
              <td>{job.stage}</td>
              <td>
                <JobBadge status={job.status} />
              </td>
              <td>{formatDate(job.started_at, true)}</td>
              <td>{formatDuration(job.duration_ms)}</td>
              <td>{job.attempt_count}</td>
              <td>
                {job.retryable && retry ? (
                  <button className="ops-link" disabled={pending} onClick={() => retry(job)}>
                    Retry <RotateCcw size={13} />
                  </button>
                ) : (
                  <button className="ops-link" onClick={() => open(job)}>
                    View <ChevronRight size={13} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
