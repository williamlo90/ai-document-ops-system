import { useOutletContext } from 'react-router-dom'
import type { ProductRole, SessionInfo, WorkspaceSummary } from './types'

export type ShellContext = {
  session: SessionInfo
  role: ProductRole
  workspace?: WorkspaceSummary
  refreshWorkspace: () => void
}

export function useShell(): ShellContext {
  return useOutletContext<ShellContext>()
}
