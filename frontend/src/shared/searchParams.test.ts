import { describe, expect, it, vi } from 'vitest'
import { updateSearchParams, type SearchParamSetter } from './searchParams'

describe('updateSearchParams', () => {
  it('preserves unrelated values while setting and removing requested keys', () => {
    const setterMock = vi.fn()
    const setter = setterMock as unknown as SearchParamSetter

    updateSearchParams(new URLSearchParams('keep=yes&remove=old'), setter, {
      page: '2',
      remove: null,
      empty: '',
    })

    expect(setterMock).toHaveBeenCalledOnce()
    const next = setterMock.mock.calls[0][0] as URLSearchParams
    expect(next.toString()).toBe('keep=yes&page=2')
  })
})
