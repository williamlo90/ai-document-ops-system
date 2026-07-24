import { AlertTriangle, CheckCircle2, CircleHelp } from 'lucide-react'
import { humanize } from '../../../shared/format'
import { Button, Panel } from '../../../shared/ui'
import { systemTabs, type SystemTab } from '../selectors'
import type { SystemDashboard } from '../types'

export function OverallBanner({ data, open }: { data: SystemDashboard; open: () => void }) {
  const icon =
    data.overall.status === 'operational' ? (
      <CheckCircle2 />
    ) : data.overall.status === 'unknown' ? (
      <CircleHelp />
    ) : (
      <AlertTriangle />
    )
  return (
    <Panel className={`system-overall is-${data.overall.status}`}>
      <span>{icon}</span>
      <div>
        <strong>{data.overall.title}</strong>
        <p>{data.overall.detail}</p>
      </div>
      <Button onClick={open}>View status details</Button>
    </Panel>
  )
}

export function OperationsSummary({
  data,
  setTab,
}: {
  data: SystemDashboard
  setTab: (tab: SystemTab, filter?: string | null) => void
}) {
  const items = [
    {
      label: 'Processing now',
      value: data.kpis.processing_now,
      action: () => setTab('processing', 'active'),
    },
    { label: 'Waiting', value: data.kpis.waiting, action: () => setTab('processing', 'waiting') },
    {
      label: 'Needs attention',
      value: data.kpis.needs_attention,
      action: () => setTab('processing', 'attention'),
    },
  ]
  return (
    <Panel className="operations-summary" ariaLabel="Processing summary">
      {items.map((item) => (
        <button key={item.label} onClick={item.action}>
          <small>{item.label}</small>
          <strong>{item.value}</strong>
        </button>
      ))}
    </Panel>
  )
}

export function SystemTabs({
  active,
  select,
}: {
  active: SystemTab
  select: (value: SystemTab) => void
}) {
  return (
    <div className="system-tabs" role="tablist" aria-label="System views">
      {systemTabs.map((item) => (
        <button
          key={item}
          role="tab"
          aria-selected={active === item}
          className={active === item ? 'is-active' : ''}
          onClick={() => select(item)}
        >
          {humanize(item)}
        </button>
      ))}
    </div>
  )
}
