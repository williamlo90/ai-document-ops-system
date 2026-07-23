import { AlertTriangle, CheckCircle2, ChevronRight, X } from 'lucide-react'
import { formatDate, humanize } from '../../invoices/format'
import { Button, EmptyState, Panel, StatusBadge } from '../../../shared/ui'
import { filterSystemJobs } from '../selectors'
import type {
  SystemAudit,
  SystemDashboard,
  SystemIntegration,
  SystemJob,
  SystemService,
} from '../types'
import { JobTable, ServiceBadge, ServiceIcon } from './OperationsPrimitives'

export function StatusView({
  data,
  openService,
}: {
  data: SystemDashboard
  openService: (item: SystemService) => void
}) {
  const hasUptimeHistory = data.services.some((service) => service.uptime !== null)
  return (
    <div className="system-status-view">
      <Panel className="system-service-panel">
        <header>
          <div>
            <h2>Core service status</h2>
            <p>
              {hasUptimeHistory
                ? 'Current checks and observed workspace activity.'
                : 'Current checks only. Uptime history is not available yet.'}
            </p>
          </div>
        </header>
        <div className="ops-table-wrap">
          <table className="ops-table system-service-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Status</th>
                {hasUptimeHistory ? <th>Uptime</th> : null}
                <th>Last observation</th>
                <th>Recent activity</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {data.services.map((service) => (
                <tr
                  key={service.id}
                  className={
                    service.status === 'degraded' || service.status === 'unavailable'
                      ? 'is-attention'
                      : ''
                  }
                >
                  <td>
                    <ServiceIcon id={service.id} />
                    {service.name}
                  </td>
                  <td>
                    <ServiceBadge status={service.status} />
                  </td>
                  {hasUptimeHistory ? <td>{service.uptime_label}</td> : null}
                  <td>
                    {service.observed_at ? formatDate(service.observed_at, true) : 'Not observed'}
                  </td>
                  <td>{service.activity}</td>
                  <td>
                    <button className="ops-link" onClick={() => openService(service)}>
                      {service.status === 'degraded' || service.status === 'unavailable'
                        ? 'Investigate'
                        : 'View'}{' '}
                      <ChevronRight size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}

export function ProcessingView({
  data,
  filter,
  stage,
  clear,
  openJob,
  retry,
  pending,
}: {
  data: SystemDashboard
  filter: string | null
  stage: string | null
  clear: () => void
  openJob: (item: SystemJob) => void
  retry: (item: SystemJob) => void
  pending: boolean
}) {
  const jobs = filterSystemJobs(data.recent_jobs, filter, stage)
  return (
    <Panel className="system-processing-panel">
      <header>
        <div>
          <h2>Processing activity</h2>
          <p>Sanitized job state for this workspace.</p>
        </div>
        {filter || stage ? (
          <button className="system-filter-chip" onClick={clear}>
            {filter ? humanize(filter) : humanize(stage!)} <X size={13} />
          </button>
        ) : null}
      </header>
      {jobs.length ? (
        <JobTable jobs={jobs} open={openJob} retry={retry} pending={pending} />
      ) : (
        <EmptyState
          title="No processing activity matches this view"
          body="Clear the current filter or wait for new invoice processing."
          action={<Button onClick={clear}>Clear filter</Button>}
        />
      )}
    </Panel>
  )
}

export function IntegrationsView({
  data,
  open,
}: {
  data: SystemIntegration[]
  open: (item: SystemIntegration) => void
}) {
  return (
    <Panel className="system-integrations-panel">
      <header>
        <div>
          <h2>Connected services</h2>
          <p>Configuration and observed state without credentials or raw provider responses.</p>
        </div>
      </header>
      <div className="system-integration-list">
        {data.map((item) => (
          <button key={item.id} onClick={() => open(item)}>
            <ServiceIcon id={item.id} />
            <span>
              <strong>{item.name}</strong>
              <small>{item.provider || 'Built-in service'}</small>
            </span>
            <ServiceBadge status={item.status} />
            <ChevronRight size={16} />
          </button>
        ))}
      </div>
    </Panel>
  )
}

export function AuditView({
  data,
  open,
}: {
  data: SystemAudit[]
  open: (item: SystemAudit) => void
}) {
  return (
    <Panel className="system-audit-panel">
      <header>
        <div>
          <h2>Audit activity</h2>
          <p>Immutable business events; raw payloads and secrets are not shown.</p>
        </div>
        <a className="ops-button ops-button--secondary" href="/operations/audit.csv">
          Download CSV
        </a>
      </header>
      {data.length ? (
        <div className="ops-table-wrap">
          <table className="ops-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Target</th>
                <th>Result</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.id}>
                  <td>{formatDate(item.timestamp, true)}</td>
                  <td>{item.actor}</td>
                  <td>{item.action}</td>
                  <td>{item.target}</td>
                  <td>
                    <StatusBadge tone="neutral">{humanize(item.result)}</StatusBadge>
                  </td>
                  <td>
                    <button className="ops-link" onClick={() => open(item)}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No audit activity yet"
          body="Upload and review events will appear here."
        />
      )}
    </Panel>
  )
}

export function AttentionPanel({
  data,
  open,
}: {
  data: SystemDashboard
  open: (target: string, kind: string) => void
}) {
  return (
    <Panel className="system-attention" ariaLabel="Needs attention">
      <section>
        <header>
          <h2>Needs attention</h2>
          <span>{data.alerts.length}</span>
        </header>
        {data.alerts.length ? (
          data.alerts.slice(0, 4).map((alert) => (
            <button key={alert.id} onClick={() => open(alert.target_id, alert.kind)}>
              <AlertTriangle size={17} />
              <span>
                <strong>{alert.title}</strong>
                <small>{alert.detail}</small>
              </span>
              <ChevronRight size={15} />
            </button>
          ))
        ) : (
          <div className="system-healthy">
            <CheckCircle2 size={21} />
            <span>
              <strong>No unresolved alerts</strong>
              <small>Current observed checks do not require action.</small>
            </span>
          </div>
        )}
      </section>
    </Panel>
  )
}
