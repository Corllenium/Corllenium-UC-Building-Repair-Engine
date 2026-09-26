import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useErrorsDoc, errorText } from './useErrorsDoc'
import type { Catalogue } from '../utils/errorsDoc'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const validCat: Catalogue = {
  built_from: { commit: 'abc1234', date: '2026-09-26 12:00' },
  origin: ['intro'],
  models: [{ id: 'A', name: 'model_a', role: 'r', numbers: {}, source: 's' }],
  kinds: [
    {
      id: 'gridlines', title: 'T', summary: 'S', color: '#1f5bff',
      models: { A: { status: 'fixed', count: '1' } },
      what: 'W', find: ['F'], why: 'Y', unity: ['U'], solution: ['S1'], done: ['D'], remain: 'R',
      engine_files: ['vis/exposure.py'], examples: [], sources: ['report.json'],
    },
  ],
  engine_mistakes: [],
  other_screenshots: [],
}

describe('useErrorsDoc', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
  })
  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('load sets catalogue and validation from two JSON responses', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(validCat))
      .mockResolvedValueOnce(jsonResponse({ version: 1, verdicts: {} })) as unknown as typeof fetch

    const { load, catalogue, validation, loadError, validationError } = useErrorsDoc()
    await load()

    expect(catalogue.value).toEqual(validCat)
    expect(validation.value).toEqual({ version: 1, verdicts: {} })
    expect(loadError.value).toBe('')
    expect(validationError.value).toBe(false)
  })

  it('sets loadError to the missing-from-build message for a non-JSON errors.json response', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(new Response('<html></html>', { status: 200, headers: { 'Content-Type': 'text/html' } }))
      .mockResolvedValueOnce(jsonResponse({ version: 1, verdicts: {} })) as unknown as typeof fetch

    const { load, catalogue, loadError } = useErrorsDoc()
    await load()

    expect(loadError.value).toBe('The documentation file is missing from this build (/docs/errors.json)')
    expect(catalogue.value).toBeNull()
  })

  it('fills loadProblems and leaves catalogue null for an invalid catalogue', async () => {
    const badCat: Catalogue = { ...validCat, kinds: [{ ...validCat.kinds[0], title: ' ' }] }
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(badCat))
      .mockResolvedValueOnce(jsonResponse({ version: 1, verdicts: {} })) as unknown as typeof fetch

    const { load, catalogue, loadProblems, loadError } = useErrorsDoc()
    await load()

    expect(catalogue.value).toBeNull()
    expect(loadProblems.value).toEqual(['gridlines: "title" is empty'])
    expect(loadError.value).toBe('The documentation file has 1 problems:')
  })

  it('sets validationError and still loads the catalogue when the validation GET fails', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(validCat))
      .mockResolvedValueOnce(new Response('', { status: 500 })) as unknown as typeof fetch

    const { load, catalogue, validationError } = useErrorsDoc()
    await load()

    expect(catalogue.value).toEqual(validCat)
    expect(validationError.value).toBe(true)
  })

  it('sends two saveVerdict calls for the same kind/model one after the other', async () => {
    const calls: string[] = []
    let resolveFirst!: (r: Response) => void
    const firstPromise = new Promise<Response>(res => { resolveFirst = res })
    let secondCalled = false

    globalThis.fetch = vi.fn((url: unknown, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${String(url)}`)
      if (calls.length === 1) return firstPromise
      secondCalled = true
      return Promise.resolve(jsonResponse({ kind: 'gridlines', model: 'A', entry: null }))
    }) as unknown as typeof fetch

    const { saveVerdict } = useErrorsDoc()
    const p1 = saveVerdict({ kindId: 'gridlines', modelId: 'A', verdict: 'ok', note: 'n1' })
    const p2 = saveVerdict({ kindId: 'gridlines', modelId: 'A', verdict: 'error', note: 'n2' })

    await Promise.resolve()
    await Promise.resolve()
    expect(secondCalled).toBe(false)

    resolveFirst(jsonResponse({ kind: 'gridlines', model: 'A', entry: { verdict: 'ok', note: 'n1', at: 't' } }))
    await p1
    await p2
    expect(secondCalled).toBe(true)
    expect(calls.length).toBe(2)
  })

  it('does not block the next save for the same key after a failed save', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(new Response('', { status: 500 }))
      .mockResolvedValueOnce(jsonResponse({ kind: 'gridlines', model: 'A', entry: { verdict: 'ok', note: '', at: 't' } })) as unknown as typeof fetch

    const { saveVerdict, validation } = useErrorsDoc()
    const onError = vi.fn()
    await saveVerdict({ kindId: 'gridlines', modelId: 'A', verdict: 'error', note: '' }, onError)
    expect(onError).toHaveBeenCalledWith('HTTP 500')

    await saveVerdict({ kindId: 'gridlines', modelId: 'A', verdict: 'ok', note: '' })
    expect(validation.value?.verdicts['gridlines']?.A?.verdict).toBe('ok')
  })

  it('updates validation on a successful save, then clears it on a null verdict', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ kind: 'gridlines', model: 'A', entry: { verdict: 'ok', note: 'n', at: 't1' } }))
      .mockResolvedValueOnce(jsonResponse({ kind: 'gridlines', model: 'A', entry: null })) as unknown as typeof fetch

    const { saveVerdict, validation } = useErrorsDoc()
    await saveVerdict({ kindId: 'gridlines', modelId: 'A', verdict: 'ok', note: 'n' })
    expect(validation.value).toEqual({ version: 1, verdicts: { gridlines: { A: { verdict: 'ok', note: 'n', at: 't1' } } } })

    await saveVerdict({ kindId: 'gridlines', modelId: 'A', verdict: null, note: 'n' })
    expect(validation.value).toEqual({ version: 1, verdicts: {} })
  })

  it('errorText reads the 422 detail message and falls back to HTTP <status>', () => {
    expect(errorText(422, { detail: [{ msg: 'String should have at most 2000 characters' }] }))
      .toBe('String should have at most 2000 characters')
    expect(errorText(500, {})).toBe('HTTP 500')
  })
})
