import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ApiError } from './client'
import { fetchHealth, fetchSuggestions, reaskSuggestion, reviewSuggestion } from './decide'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('decide API', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('reviewSuggestion posts the accept body as JSON to /api/decide/review/7', async () => {
    const spy = vi.fn().mockResolvedValue(json({ id: 7, status: 'accepted' }))
    globalThis.fetch = spy
    const row = await reviewSuggestion(7, { accept: true })
    expect(row).toEqual({ id: 7, status: 'accepted' })
    expect(spy.mock.calls[0][0]).toBe('/api/decide/review/7')
    const init = spy.mock.calls[0][1]
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ accept: true })
  })

  it('reviewSuggestion sends the raw answer value: a real bool, a label, an int', async () => {
    const spy = vi.fn().mockImplementation(async () => json({ id: 1 }))
    globalThis.fetch = spy
    await reviewSuggestion(1, { answer: false })
    await reviewSuggestion(1, { answer: 'glass' })
    await reviewSuggestion(1, { answer: 2 })
    expect(spy.mock.calls.map((c) => JSON.parse(c[1].body))).toEqual([
      { answer: false },
      { answer: 'glass' },
      { answer: 2 },
    ])
  })

  it('reviewSuggestion turns a 422 into ApiError', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(json({ detail: 'answer must be one of [True, False] (right type)' }, 422))
    try {
      await reviewSuggestion(7, { answer: 'maybe' })
      expect.fail('Expected reviewSuggestion to throw ApiError')
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError)
      expect(err.status).toBe(422)
      expect(err.message).toContain('answer must be one of')
    }
  })

  it('fetchHealth reads jev_enabled', async () => {
    const spy = vi.fn().mockResolvedValue(
      json({ ok: true, jev_enabled: false, tokens_today: 0, daily_token_cap: 1000000, model: 'm' })
    )
    globalThis.fetch = spy
    const h = await fetchHealth()
    expect(h.jev_enabled).toBe(false)
    expect(h.daily_token_cap).toBe(1000000)
    expect(spy.mock.calls[0][0]).toBe('/api/decide/health')
  })

  it('fetchHealth throws ApiError with the status on 502 and 404', async () => {
    for (const status of [502, 404]) {
      globalThis.fetch = vi.fn().mockResolvedValue(new Response('<html>bad gateway</html>', { status }))
      await expect(fetchHealth()).rejects.toMatchObject({ name: 'ApiError', status })
    }
  })

  it('fetchSuggestions sends only the params that are set and returns items and counts', async () => {
    const body = { items: [{ id: 1 }], counts: { pending: 1, accepted: 0, changed: 0 } }
    const spy = vi.fn().mockImplementation(async () => json(body))
    globalThis.fetch = spy
    const out = await fetchSuggestions({ status: 'pending', type: 'mat.trim', min_conf: 0.5, q: 'wood', limit: 50, offset: 0 })
    expect(out).toEqual(body)
    const url = new URL(spy.mock.calls[0][0], 'http://x')
    expect(url.pathname).toBe('/api/decide/suggestions')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      status: 'pending', type: 'mat.trim', min_conf: '0.5', q: 'wood', limit: '50', offset: '0',
    })
    await fetchSuggestions({})
    expect(spy.mock.calls[1][0]).toBe('/api/decide/suggestions')
  })

  it('reaskSuggestion posts to /api/decide/reask/3 and surfaces a 409 as ApiError', async () => {
    const spy = vi.fn().mockResolvedValue(json({ detail: 'jev off' }, 409))
    globalThis.fetch = spy
    await expect(reaskSuggestion(3)).rejects.toMatchObject({ name: 'ApiError', status: 409, message: 'jev off' })
    expect(spy.mock.calls[0][0]).toBe('/api/decide/reask/3')
    expect(spy.mock.calls[0][1].method).toBe('POST')
  })
})
