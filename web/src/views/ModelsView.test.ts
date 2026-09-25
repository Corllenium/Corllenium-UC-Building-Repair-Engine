import { describe, it, expect } from 'vitest'
import { ApiError } from '../api/client'
import { formatErrorMessage } from '../utils/formatError'

describe('ModelsView error formatting & ApiError', () => {
  it('exposes status and retryAfter on ApiError', () => {
    const err = new ApiError('Locked', 409, 10)
    expect(err.status).toBe(409)
    expect(err.retryAfter).toBe(10)
    expect(err.message).toBe('Locked')
  })

  it('formats 409 status as export rebuilding message with retryAfter seconds', () => {
    const errWith10 = new ApiError('Locked', 409, 10)
    expect(formatErrorMessage(errWith10)).toBe('Export folder is being rebuilt, try again in 10 s')

    const errWithDefault = new ApiError('Locked', 409)
    expect(formatErrorMessage(errWithDefault)).toBe('Export folder is being rebuilt, try again in 5 s')
  })

  it('formats regular errors with their message', () => {
    const err404 = new ApiError('Model not found', 404)
    expect(formatErrorMessage(err404)).toBe('Model not found')

    const err422 = new ApiError('Manifest mismatch', 422)
    expect(formatErrorMessage(err422)).toBe('Manifest mismatch')
  })

  it('rescanModels issues POST /api/models/rescan', async () => {
    const { rescanModels } = await import('../api/client')
    const originalFetch = globalThis.fetch
    try {
      let requestedUrl = ''
      let requestedMethod = ''
      globalThis.fetch = (async (url: string, init?: RequestInit) => {
        requestedUrl = url
        requestedMethod = init?.method || 'GET'
        return {
          ok: true,
          json: async () => [{ id: 1, name: 'cube', source_file: 'cube.obj', created_at: '', versions: [] }],
        } as unknown as Response
      }) as typeof fetch

      const res = await rescanModels()
      expect(requestedUrl).toBe('/api/models/rescan')
      expect(requestedMethod).toBe('POST')
      expect(res).toHaveLength(1)
      expect(res[0].name).toBe('cube')
    } finally {
      globalThis.fetch = originalFetch
    }
  })
})
