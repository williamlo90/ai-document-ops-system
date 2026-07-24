import type { useSearchParams } from 'react-router-dom'

export type SearchParamSetter = ReturnType<typeof useSearchParams>[1]
export type SearchParamUpdates = Record<string, string | null | undefined>

export function updateSearchParams(
  current: URLSearchParams,
  setter: SearchParamSetter,
  values: SearchParamUpdates,
) {
  const next = new URLSearchParams(current)
  for (const [key, value] of Object.entries(values)) {
    if (value) next.set(key, value)
    else next.delete(key)
  }
  setter(next)
}
