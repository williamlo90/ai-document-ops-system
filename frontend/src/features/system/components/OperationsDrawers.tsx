import type { ReactNode } from 'react'
import { AlertCircle, LoaderCircle, RotateCcw, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatDate, humanize } from '../../invoices/format'
import { Button, StatusBadge } from '../../../shared/ui'
import { formatDuration } from '../selectors'
import type { SystemAudit, SystemJob, SystemService } from '../types'
import { JobBadge, ServiceBadge } from './OperationsPrimitives'

export function ServiceDrawer({ service, close }: { service: SystemService; close: () => void }) {
  return (
    <Drawer eyebrow="Service status" title={service.name} close={close}>
      <div className="system-drawer-verdict">
        <ServiceBadge status={service.status} />
        <strong>{service.provider || 'Built-in capability'}</strong>
        <span>
          {service.observed_at
            ? `Observed ${formatDate(service.observed_at, true)}`
            : 'No observed provider run'}
        </span>
      </div>
      <dl>
        <div>
          <dt>Uptime</dt>
          <dd>{service.uptime_label}</dd>
        </div>
        <div>
          <dt>Recent activity</dt>
          <dd>{service.activity}</dd>
        </div>
      </dl>
      <section>
        <h3>Evidence</h3>
        <p>{service.evidence}</p>
      </section>
      {service.affected_capability ? (
        <section className="system-impact">
          <h3>Affected</h3>
          <p>{service.affected_capability}</p>
        </section>
      ) : null}
      {service.unaffected_capability ? (
        <section>
          <h3>Still available</h3>
          <p>{service.unaffected_capability}</p>
        </section>
      ) : null}
    </Drawer>
  )
}

export function JobDrawer({
  job,
  pending,
  error,
  close,
  retry,
}: {
  job: SystemJob
  pending: boolean
  error: Error | null
  close: () => void
  retry: () => void
}) {
  return (
    <Drawer eyebrow="Processing trace" title={job.invoice} close={close}>
      <div className="system-drawer-verdict">
        <JobBadge status={job.status} />
        <strong>{job.stage}</strong>
        <span>{job.filename}</span>
      </div>
      <dl>
        <div>
          <dt>Started</dt>
          <dd>{formatDate(job.started_at, true)}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>{formatDate(job.finished_at, true)}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{formatDuration(job.duration_ms)}</dd>
        </div>
        <div>
          <dt>Attempts</dt>
          <dd>{job.attempt_count}</dd>
        </div>
      </dl>
      {job.failure_summary ? (
        <section className="system-impact">
          <h3>What happened</h3>
          <p>{job.failure_summary}</p>
        </section>
      ) : null}
      {error ? (
        <p className="system-drawer-error">
          <AlertCircle size={16} />
          {error.message}
        </p>
      ) : null}
      <footer>
        <Link className="ops-button ops-button--secondary" to={`/review/${job.document_id}`}>
          Open invoice
        </Link>
        {job.retryable ? (
          <Button variant="primary" disabled={pending} onClick={retry}>
            {pending ? <LoaderCircle className="spin" size={16} /> : <RotateCcw size={16} />}{' '}
            {pending ? 'Accepting retry...' : 'Retry processing'}
          </Button>
        ) : null}
      </footer>
    </Drawer>
  )
}

export function AuditDrawer({ audit, close }: { audit: SystemAudit; close: () => void }) {
  return (
    <Drawer eyebrow="Audit event" title={audit.action} close={close}>
      <div className="system-drawer-verdict">
        <StatusBadge tone="neutral">{humanize(audit.result)}</StatusBadge>
        <strong>{audit.target}</strong>
        <span>{formatDate(audit.timestamp, true)}</span>
      </div>
      <dl>
        <div>
          <dt>Actor</dt>
          <dd>{audit.actor}</dd>
        </div>
        <div>
          <dt>Event ID</dt>
          <dd>{audit.id}</dd>
        </div>
      </dl>
      <section>
        <h3>Record boundary</h3>
        <p>
          This view exposes the event outcome only. Raw payloads, prompts, credentials, and provider
          responses remain hidden.
        </p>
      </section>
    </Drawer>
  )
}

function Drawer({
  eyebrow,
  title,
  close,
  children,
}: {
  eyebrow: string
  title: string
  close: () => void
  children: ReactNode
}) {
  return (
    <div
      className="ops-modal-backdrop system-drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <aside
        className="system-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="system-drawer-title"
      >
        <header>
          <div>
            <span>{eyebrow}</span>
            <h2 id="system-drawer-title">{title}</h2>
          </div>
          <button className="ops-icon-button" aria-label="Close details" onClick={close}>
            <X size={19} />
          </button>
        </header>
        {children}
      </aside>
    </div>
  )
}
