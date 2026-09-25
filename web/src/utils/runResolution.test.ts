import { describe, it, expect, vi } from 'vitest'
import { resolveActiveRun } from './runResolution'
import type { FixRun } from '../api/client'

describe('resolveActiveRun (N2)', () => {
  const previousRun: FixRun = {
    id: 1,
    version_id: 1,
    status: 'completed',
    fixed_version_id: 2,
    created_at: '2026-09-25T10:00:00Z',
    report_json: { passed: true, tris_after: 100 },
  }

  const failedRun: FixRun = {
    id: 2,
    version_id: 1,
    status: 'failed',
    error: 'ValueError: non-manifold edges encountered in mesh',
    created_at: '2026-09-25T10:05:00Z',
  }

  it('keeps failed run when reloadModel fetches no fixed version run (empty placeholder avoided)', () => {
    const active = resolveActiveRun(failedRun, null)
    expect(active).toBe(failedRun)
    expect(active?.status).toBe('failed')
    expect(active?.error).toBe('ValueError: non-manifold edges encountered in mesh')
  })

  it('keeps failed run when reloadModel fetches the previous fixed version run', () => {
    const active = resolveActiveRun(failedRun, previousRun)
    expect(active).toBe(failedRun)
    expect(active?.id).toBe(2)
    expect(active?.status).toBe('failed')
    expect(active?.error).toBe('ValueError: non-manifold edges encountered in mesh')
  })

  it('loads fetched run on initial mount when latestRun is null', () => {
    const active = resolveActiveRun(null, previousRun)
    expect(active).toBe(previousRun)
    expect(active?.status).toBe('completed')
  })

  it('returns null on initial mount when there is no fixed version run', () => {
    const active = resolveActiveRun(null, null)
    expect(active).toBeNull()
  })

  it('updates to fetched run when latest run completed successfully', () => {
    const completedRun: FixRun = {
      id: 3,
      version_id: 1,
      status: 'completed',
      fixed_version_id: 4,
      created_at: '2026-09-25T10:10:00Z',
    }
    const freshFetchedRun: FixRun = {
      ...completedRun,
      report_json: { passed: true, tris_after: 80 },
    }
    const active = resolveActiveRun(completedRun, freshFetchedRun)
    expect(active).toBe(freshFetchedRun)
  })

  it('loadVersionRunOnMount fetches run for fixed version on mount (I2)', async () => {
    const { loadVersionRunOnMount } = await import('./runResolution')
    const fetchRunMock = vi.fn().mockResolvedValue(previousRun)
    const run = await loadVersionRunOnMount(2, fetchRunMock)
    expect(run).toBe(previousRun)
    expect(fetchRunMock).toHaveBeenCalledWith(2)
  })

  it('loadVersionRunOnMount returns null without fetching when no fixed version exists (I2)', async () => {
    const { loadVersionRunOnMount } = await import('./runResolution')
    const fetchRunMock = vi.fn()
    const run = await loadVersionRunOnMount(undefined, fetchRunMock)
    expect(run).toBeNull()
    expect(fetchRunMock).not.toHaveBeenCalled()
  })

  it('loadVersionRunOnMount catches fetch failure and returns null (I2)', async () => {
    const { loadVersionRunOnMount } = await import('./runResolution')
    const fetchRunMock = vi.fn().mockRejectedValue(new Error('Network error'))
    const run = await loadVersionRunOnMount(2, fetchRunMock)
    expect(run).toBeNull()
  })
})
