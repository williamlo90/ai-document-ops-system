import { Panel, SkeletonRows } from '../../../shared/ui'

export function OperationsSkeleton() {
  return (
    <div className="system-skeleton">
      <Panel>
        <SkeletonRows count={2} />
      </Panel>
      <Panel>
        <SkeletonRows count={2} />
      </Panel>
      <Panel>
        <SkeletonRows count={9} />
      </Panel>
    </div>
  )
}
