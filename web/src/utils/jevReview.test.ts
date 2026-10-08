import { describe, it, expect } from 'vitest'
import { ApiError } from '../api/client'
import {
  TABS,
  acceptAllSelection,
  answerLabel,
  errorText,
  filterRows,
  isServiceMissing,
  isServiceUnreachable,
  serviceNote,
  mergeResults,
  optionLabels,
  optionValues,
  runAcceptAll,
  suggestionParams,
  textureName,
  topAlternatives,
  type Question,
  type Suggestion,
} from './jevReview'

const noul: Question = { kind: 'noul', instructions: 'Is it a trim?', criteria: null, qtype: 'mat.trim', subject: 'Wood_1' }
const choice: Question = {
  kind: 'choice', instructions: 'Which kind?', qtype: 'mat.category', subject: 'Wood_1',
  criteria: { wood: null, glass: 'see-through', stone: null },
}
const score: Question = {
  kind: 'score', instructions: 'How bad?', qtype: 'repair.order', subject: 'x',
  criteria: ['fine', 'poor', 'bad'],
}

function row(over: Partial<Suggestion>): Suggestion {
  return {
    id: 1, qtype: 'mat.trim', subject: 'Wood_1', question: noul, answer: true, confidence: 0.9,
    probabilities: {}, model: 'm', source: 'jev', status: 'pending', owner_answer: null,
    reviewed_at: null, reviewed_by: null, created_at: '2026-10-08T00:00:00Z', ...over,
  }
}

describe('TABS', () => {
  it('has Materials and Campus map live, the other three not', () => {
    expect(TABS.map((t) => [t.label, t.available])).toEqual([
      ['Materials', true],
      ['Campus map', true],
      ['Next repair step', false],
      ['Review order', false],
      ['Fix tie-breaks', false],
    ])
    expect(TABS[0].qtypes).toEqual(['mat.category', 'mat.trim'])
    expect(TABS[1].qtypes).toEqual(['inv.building', 'inv.type', 'inv.floor', 'inv.duplicate'])
  })
  it('keeps the reserved qtypes of the three tabs that are not live yet', () => {
    expect(TABS.find((t) => t.key === 'next_step')!.qtypes).toEqual(['repair.next_step'])
    expect(TABS.find((t) => t.key === 'review_order')!.qtypes).toEqual(['review.priority'])
    expect(TABS.find((t) => t.key === 'tie_breaks')!.qtypes).toEqual(['e5.winner', 'e4.same_look', 'e8.opening_kind'])
  })
})

describe('filterRows', () => {
  const rows = [
    row({ id: 1, subject: 'Wood_Planks', status: 'pending', confidence: 0.95 }),
    row({ id: 2, subject: 'wood_trim', status: 'accepted', confidence: 0.6 }),
    row({ id: 3, subject: 'Glass', status: 'pending', confidence: 0.4 }),
    row({ id: 4, subject: 'Stone', status: 'changed', confidence: 0.8 }),
  ]
  it('filters by status', () => {
    expect(filterRows(rows, { status: 'pending', minConf: 0, text: '' }).map((r) => r.id)).toEqual([1, 3])
    expect(filterRows(rows, { status: 'all', minConf: 0, text: '' }).map((r) => r.id)).toEqual([1, 2, 3, 4])
  })
  it('filters by minimum confidence, inclusive', () => {
    expect(filterRows(rows, { status: 'all', minConf: 0.8, text: '' }).map((r) => r.id)).toEqual([1, 4])
  })
  it('searches the subject, case-insensitively', () => {
    expect(filterRows(rows, { status: 'all', minConf: 0, text: 'WOOD' }).map((r) => r.id)).toEqual([1, 2])
    expect(filterRows(rows, { status: 'pending', minConf: 0.5, text: 'wood' }).map((r) => r.id)).toEqual([1])
  })
})

describe('topAlternatives', () => {
  it('leaves out the chosen answer and sorts by probability', () => {
    const r = row({
      question: choice, answer: 'wood',
      probabilities: { glass: 0.1, wood: 0.6, stone: 0.3 },
    })
    expect(topAlternatives(r).map((a) => [a.label, a.probability])).toEqual([['stone', 0.3], ['glass', 0.1]])
  })
  it('takes at most n', () => {
    const r = row({
      question: choice, answer: 'wood',
      probabilities: { glass: 0.1, wood: 0.6, stone: 0.3 },
    })
    expect(topAlternatives(r, 1).map((a) => a.label)).toEqual(['stone'])
  })
  it('reads Noul string keys and Score string indexes', () => {
    const n = row({ question: noul, answer: true, probabilities: { true: 0.7, false: 0.3 } })
    expect(topAlternatives(n)).toEqual([{ value: false, label: 'no', probability: 0.3 }])
    const s = row({ question: score, answer: 1, probabilities: { '0': 0.2, '1': 0.5, '2': 0.3 } })
    expect(topAlternatives(s).map((a) => [a.value, a.label])).toEqual([[2, 'bad'], [0, 'fine']])
  })
  it('gives nothing for the empty probabilities of a pilot import', () => {
    expect(topAlternatives(row({ question: choice, answer: 'wood', probabilities: {} }))).toEqual([])
  })
})

describe('acceptAllSelection', () => {
  it('takes only pending rows at or above the threshold', () => {
    const rows = [
      row({ id: 1, status: 'pending', confidence: 0.9 }),
      row({ id: 2, status: 'pending', confidence: 0.95 }),
      row({ id: 3, status: 'pending', confidence: 0.89 }),
      row({ id: 4, status: 'accepted', confidence: 0.99 }),
      row({ id: 5, status: 'changed', confidence: 0.99 }),
    ]
    expect(acceptAllSelection(rows, 0.9)).toEqual([1, 2])
    expect(acceptAllSelection([], 0.9)).toEqual([])
  })
})

describe('optionLabels and optionValues', () => {
  it('gives Noul yes/no with raw booleans', () => {
    expect(optionLabels(noul)).toEqual(['yes', 'no'])
    expect(optionValues(noul)).toEqual([true, false])
  })
  it('gives Choice the keys, sent as the label', () => {
    expect(optionLabels(choice)).toEqual(['wood', 'glass', 'stone'])
    expect(optionValues(choice)).toEqual(['wood', 'glass', 'stone'])
  })
  it('gives Score the levels, sent as the int index', () => {
    expect(optionLabels(score)).toEqual(['fine', 'poor', 'bad'])
    expect(optionValues(score)).toEqual([0, 1, 2])
  })
  it('Change sends the raw value of the chosen display label', () => {
    const pick = (q: Question, label: string) => optionValues(q)[optionLabels(q).indexOf(label)]
    expect(pick(noul, 'no')).toBe(false)
    expect(pick(noul, 'yes')).toBe(true)
    expect(pick(choice, 'glass')).toBe('glass')
    expect(pick(score, 'bad')).toBe(2)
  })
})

describe('answerLabel', () => {
  it('shows an answer value as its display label', () => {
    expect(answerLabel(noul, true)).toBe('yes')
    expect(answerLabel(noul, false)).toBe('no')
    expect(answerLabel(choice, 'glass')).toBe('glass')
    expect(answerLabel(score, 2)).toBe('bad')
    expect(answerLabel(score, 1.6)).toBe('bad')
    expect(answerLabel(noul, null)).toBe('no answer')
  })
})

describe('textureName', () => {
  it('takes the texture file name out of the question instructions', () => {
    const q: Question = {
      ...choice,
      instructions: "The material is named 'Wood_1'. Its texture file is named 'oak_planks_-1.png'. Which kind?",
    }
    expect(textureName(row({ question: q }))).toBe('oak_planks_-1.png')
  })
  it('is null when the material has no texture', () => {
    const q: Question = { ...choice, instructions: "The material is named 'Wood_1'. It has no texture. Which kind?" }
    expect(textureName(row({ question: q }))).toBeNull()
  })
})

describe('isServiceMissing and isServiceUnreachable', () => {
  it('a 404 ApiError means the service runs on the VPS, nothing else does', () => {
    expect(isServiceMissing(new ApiError('x', 404))).toBe(true)
    expect(isServiceMissing(new ApiError('x', 502))).toBe(false)
    expect(isServiceMissing(new ApiError('x', 403))).toBe(false)
    expect(isServiceMissing(new Error('x'))).toBe(false)
  })
  it('a 502 ApiError means the service is unreachable, nothing else does', () => {
    expect(isServiceUnreachable(new ApiError('x', 502))).toBe(true)
    expect(isServiceUnreachable(new ApiError('x', 404))).toBe(false)
    expect(isServiceUnreachable(new ApiError('x', 500))).toBe(false)
    expect(isServiceUnreachable(new Error('x'))).toBe(false)
  })
  it('serviceNote gives the banner text: 502 unreachable, only 404 runs on the VPS, else none', () => {
    expect(serviceNote(new ApiError('x', 502))).toBe('Jev service unreachable')
    expect(serviceNote(new ApiError('x', 404))).toBe('Jev service runs on the VPS')
    expect(serviceNote(new ApiError('x', 403))).toBeNull()
    expect(serviceNote(new Error('x'))).toBeNull()
  })
})

describe('mergeResults', () => {
  it('concatenates items and adds the counts', () => {
    const merged = mergeResults([
      { items: [row({ id: 1 })], counts: { pending: 1, accepted: 2, changed: 0 } },
      { items: [row({ id: 2 })], counts: { pending: 3, accepted: 0, changed: 1 } },
    ])
    expect(merged.items.map((r) => r.id)).toEqual([1, 2])
    expect(merged.counts).toEqual({ pending: 4, accepted: 2, changed: 1 })
  })
})

describe('threshold validation', () => {
  const rows = [row({ id: 1, status: 'pending', confidence: 0.95 }), row({ id: 2, status: 'pending', confidence: 0.1 })]
  it('acceptAllSelection selects nothing for an empty, NaN or non-finite threshold', () => {
    expect(acceptAllSelection(rows, '' as unknown as number)).toEqual([])
    expect(acceptAllSelection(rows, NaN)).toEqual([])
    expect(acceptAllSelection(rows, Infinity)).toEqual([])
    expect(acceptAllSelection(rows, undefined as unknown as number)).toEqual([])
    expect(acceptAllSelection(rows, 0)).toEqual([1, 2])
  })
  it('filterRows shows nothing for an empty or NaN minimum confidence', () => {
    expect(filterRows(rows, { status: 'all', minConf: '' as unknown as number, text: '' })).toEqual([])
    expect(filterRows(rows, { status: 'all', minConf: NaN, text: '' })).toEqual([])
    expect(filterRows(rows, { status: 'all', minConf: 0, text: '' }).length).toBe(2)
  })
})

describe('suggestionParams', () => {
  it('sends status, min_conf and q to the server, trimmed, with the question type', () => {
    expect(suggestionParams({ status: 'pending', minConf: 0.5, text: ' wood ' }, 'mat.trim', 500)).toEqual({
      type: 'mat.trim', status: 'pending', min_conf: 0.5, q: 'wood', limit: 500,
    })
  })
  it('leaves status out for all and q out when empty, but keeps min_conf 0', () => {
    expect(suggestionParams({ status: 'all', minConf: 0, text: '  ' }, 'inv.floor', 500)).toEqual({
      type: 'inv.floor', min_conf: 0, limit: 500,
    })
  })
  it('is null when the minimum confidence is not a number', () => {
    expect(suggestionParams({ status: 'all', minConf: '' as unknown as number, text: '' }, 'x', 500)).toBeNull()
    expect(suggestionParams({ status: 'all', minConf: NaN, text: '' }, 'x', 500)).toBeNull()
  })
})

describe('runAcceptAll', () => {
  const ok = async () => undefined
  it('accepts every id and reports nothing stopped', async () => {
    const calls: number[] = []
    const res = await runAcceptAll([1, 2, 3], async (id) => { calls.push(id) })
    expect(calls).toEqual([1, 2, 3])
    expect(res).toEqual({ done: [1, 2, 3], failed: [], stoppedAfter: null })
  })
  it('clears the errors of every id at the start, through onStart', async () => {
    let started: number[] = []
    await runAcceptAll([4, 5], ok, { onStart: (ids) => { started = ids } })
    expect(started).toEqual([4, 5])
  })
  it('continues on a per-row 404 (unknown suggestion), 422 and 409', async () => {
    const errors: Record<number, ApiError> = {
      1: new ApiError('unknown suggestion', 404),
      2: new ApiError('answer must be one of', 422),
      3: new ApiError('conflict', 409),
    }
    const res = await runAcceptAll([1, 2, 3, 4], async (id) => { if (errors[id]) throw errors[id] })
    expect(res.done).toEqual([4])
    expect(res.failed.map((f) => f.id)).toEqual([1, 2, 3])
    expect(res.stoppedAfter).toBeNull()
  })
  it('stops at the first service-missing 404 or 502, 401, 403 or non-ApiError error', async () => {
    const stoppers: unknown[] = [
      new ApiError('Not Found', 404), new ApiError('bad gateway', 502), new ApiError('no user', 401),
      new ApiError('owner only', 403), new ApiError('boom', 500), new TypeError('Failed to fetch'),
    ]
    for (const err of stoppers) {
      const calls: number[] = []
      const res = await runAcceptAll([1, 2, 3, 4], async (id) => {
        calls.push(id)
        if (id === 3) throw err
      })
      expect(calls).toEqual([1, 2, 3])
      expect(res.done).toEqual([1, 2])
      expect(res.failed.map((f) => f.id)).toEqual([3])
      expect(res.stoppedAfter).toBe(2)
    }
  })
  it('reports the failure per id with its error', async () => {
    const err = new ApiError('unknown suggestion', 404)
    const res = await runAcceptAll([9], async () => { throw err })
    expect(res.failed).toEqual([{ id: 9, error: err }])
  })
})

describe('errorText', () => {
  it('gives a plain message as it is', () => {
    expect(errorText(new ApiError('jev off', 409))).toBe('jev off')
    expect(errorText(new Error('x'))).toBe('x')
  })
  it('reads the 422 list form of detail (a JSON list of {loc, msg, type})', () => {
    const detail = JSON.stringify([
      { loc: ['body', 'accept'], msg: 'Input should be a valid boolean', type: 'bool_type' },
      { loc: ['path', 'id'], msg: 'Input should be a valid integer', type: 'int_parsing' },
    ])
    expect(errorText(new ApiError(detail, 422)))
      .toBe('body.accept: Input should be a valid boolean; path.id: Input should be a valid integer')
  })
  it('keeps a message that merely looks like JSON but is not a detail list', () => {
    expect(errorText(new ApiError('[not json', 422))).toBe('[not json')
    expect(errorText(new ApiError('[1,2]', 422))).toBe('[1,2]')
  })
})
