import type { ExportWorkspaceResponse } from '../types'
import { exportViewCount, exportViews, type ExportView } from '../selectors'

const labels: Record<ExportView, string> = {
  ready: 'Ready',
  in_batch: 'In batch',
  exported: 'Exported',
  blocked: 'Blocked',
  drafts: 'Drafts',
}

export function ExportTabs({
  data,
  active,
  setView,
}: {
  data?: ExportWorkspaceResponse
  active: ExportView
  setView: (view: ExportView) => void
}) {
  return (
    <div className="export-tabs" role="tablist" aria-label="Export status">
      {exportViews.map((view) => {
        const count = exportViewCount(data, view, active)
        return (
          <button
            key={view}
            role="tab"
            aria-selected={active === view}
            className={active === view ? 'is-active' : ''}
            onClick={() => setView(view)}
            onFocus={(event) =>
              event.currentTarget.scrollIntoView({ block: 'nearest', inline: 'center' })
            }
          >
            {labels[view]}
            {count == null ? null : <span>{count}</span>}
          </button>
        )
      })}
    </div>
  )
}
