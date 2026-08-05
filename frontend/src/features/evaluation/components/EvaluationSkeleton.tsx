import { Panel, SkeletonRows } from '../../../shared/ui'

export function EvaluationSkeleton() {
  return (
    <div className="evaluation-skeleton">
      <Panel>
        <SkeletonRows count={2} />
      </Panel>
      <div className="evaluation-main-grid">
        <Panel>
          <SkeletonRows count={8} />
        </Panel>
        <Panel>
          <SkeletonRows count={7} />
        </Panel>
      </div>
    </div>
  )
}
