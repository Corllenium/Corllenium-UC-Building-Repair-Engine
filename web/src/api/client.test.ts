import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ApiError, fetchSourceFiles, fetchModels } from './client'

describe('client API and ApiError', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('parses Retry-After header and status into ApiError on 409 response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Source folder undergoing rebuild' }), {
        status: 409,
        statusText: 'Conflict',
        headers: {
          'Content-Type': 'application/json',
          'Retry-After': '5',
        },
      })
    )

    try {
      await fetchSourceFiles()
      expect.fail('Expected fetchSourceFiles to throw ApiError')
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError)
      expect(err.status).toBe(409)
      expect(err.retryAfter).toBe(5)
      expect(err.message).toBe('Source folder undergoing rebuild')
    }
  })

  it('parses error without Retry-After header', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Unprocessable entity' }), {
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: { 'Content-Type': 'application/json' },
      })
    )

    try {
      await fetchModels()
      expect.fail('Expected fetchModels to throw ApiError')
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError)
      expect(err.status).toBe(422)
      expect(err.retryAfter).toBeUndefined()
      expect(err.message).toBe('Unprocessable entity')
    }
  })

  it('returns parsed json on 200 response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ file: 'model.obj', size_bytes: 100 }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    const files = await fetchSourceFiles()
    expect(files).toEqual([{ file: 'model.obj', size_bytes: 100 }])
  })

  it('does not auto-retry on 409, throwing ApiError on the single attempt', async () => {
    let callCount = 0
    globalThis.fetch = vi.fn().mockImplementation(async () => {
      callCount++
      return new Response(JSON.stringify({ detail: 'Locked' }), {
        status: 409,
        headers: { 'Content-Type': 'application/json', 'Retry-After': '5' },
      })
    })

    await expect(fetchSourceFiles()).rejects.toThrow(ApiError)
    expect(callCount).toBe(1)
  })
})
