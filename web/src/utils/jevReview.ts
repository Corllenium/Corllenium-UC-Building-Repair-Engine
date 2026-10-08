// Logic of the /jev review page. Plain functions, no Vue, so Vitest covers them.
import { ApiError } from '../api/client'

export type Status = 'pending' | 'accepted' | 'changed'
/** An answer as it travels on the wire: a bool for Noul, a label for Choice, an int level for Score. */
export type AnswerValue = boolean | string | number | null

export interface Question {
  kind: 'noul' | 'choice' | 'score'
  instructions: string
  /** Noul: null. Choice: option label -> description (or null). Score: the list of level texts. */
  criteria: Record<string, string | null> | string[] | null
  qtype: string
  subject: string
}

export interface Suggestion {
  id: number
  qtype: string
  subject: string
  question: Question
  answer: AnswerValue
  confidence: number
  /** String-keyed, and `{}` for pilot imports. */
  probabilities: Record<string, number>
  model: string | null
  source: string
  status: Status
  owner_answer: AnswerValue
  reviewed_at: string | null
  reviewed_by: string | null
  created_at: string
}

export interface Counts {
  pending: number
  accepted: number
  changed: number
}

export interface SuggestionsReply {
  items: Suggestion[]
  counts: Partial<Counts>
}

export type ReviewBody = { accept: true } | { answer: boolean | string | number }

export interface DecideHealth {
  ok: boolean
  jev_enabled: boolean
  tokens_today: number
  daily_token_cap: number
  model: string
}

export interface Tab {
  key: string
  label: string
  qtypes: string[]
  available: boolean
}

export const TABS: Tab[] = [
  { key: 'materials', label: 'Materials', qtypes: ['mat.category', 'mat.trim'], available: true },
  {
    key: 'campus', label: 'Campus map',
    qtypes: ['inv.building', 'inv.type', 'inv.floor', 'inv.duplicate'], available: true,
  },
  { key: 'next_step', label: 'Next repair step', qtypes: ['repair.next_step'], available: false },
  { key: 'review_order', label: 'Review order', qtypes: ['repair.review_order'], available: false },
  { key: 'tie_breaks', label: 'Fix tie-breaks', qtypes: ['repair.tie_break'], available: false },
]

export interface RowFilter {
  /** 'all' or a status. */
  status: string
  minConf: number
  text: string
}

export function filterRows(rows: Suggestion[], f: RowFilter): Suggestion[] {
  const needle = f.text.trim().toLowerCase()
  return rows.filter(
    (r) =>
      (f.status === 'all' || f.status === '' || r.status === f.status) &&
      r.confidence >= f.minConf &&
      (needle === '' || r.subject.toLowerCase().includes(needle))
  )
}

/** The display labels of a question's options, in order. */
export function optionLabels(q: Question): string[] {
  if (q.kind === 'noul') return ['yes', 'no']
  if (q.kind === 'choice') return Object.keys((q.criteria ?? {}) as Record<string, unknown>)
  return [...((q.criteria ?? []) as string[])]
}

/** The RAW value to send for each label of `optionLabels`: true/false, the label itself, the int index. */
export function optionValues(q: Question): Array<boolean | string | number> {
  if (q.kind === 'noul') return [true, false]
  if (q.kind === 'choice') return Object.keys((q.criteria ?? {}) as Record<string, unknown>)
  return ((q.criteria ?? []) as string[]).map((_, i) => i)
}

function sameValue(q: Question, a: AnswerValue, b: AnswerValue): boolean {
  if (q.kind === 'score' && typeof a === 'number' && typeof b === 'number') return Math.round(a) === Math.round(b)
  return a === b
}

/** The display label of an answer value (Jev's or the owner's). */
export function answerLabel(q: Question, value: AnswerValue): string {
  if (value === null || value === undefined) return 'no answer'
  const i = optionValues(q).findIndex((v) => sameValue(q, v, value))
  if (i >= 0) return optionLabels(q)[i]
  return String(value)
}

export interface Alternative {
  value: boolean | string | number
  label: string
  probability: number
}

/** The probability keys are strings: 'true'/'false' for Noul, labels for Choice, '0'..'n' for Score. */
function keyValue(q: Question, key: string): boolean | string | number | undefined {
  if (q.kind === 'noul') {
    const k = key.toLowerCase()
    if (k === 'true' || k === 'yes') return true
    if (k === 'false' || k === 'no') return false
    return undefined
  }
  if (q.kind === 'choice') return optionValues(q).includes(key) ? key : undefined
  const n = Number(key)
  return Number.isInteger(n) && n >= 0 && n < optionValues(q).length ? n : undefined
}

/** The most likely answers other than the chosen one, most likely first. */
export function topAlternatives(row: Suggestion, n = 2): Alternative[] {
  const out: Alternative[] = []
  for (const [key, probability] of Object.entries(row.probabilities ?? {})) {
    const value = keyValue(row.question, key)
    if (value === undefined || sameValue(row.question, value, row.answer)) continue
    out.push({ value, label: answerLabel(row.question, value), probability })
  }
  return out.sort((a, b) => b.probability - a.probability).slice(0, n)
}

/** The ids "Accept all shown" would accept: pending rows at or above `minConf`. */
export function acceptAllSelection(rows: Suggestion[], minConf: number): number[] {
  return rows.filter((r) => r.status === 'pending' && r.confidence >= minConf).map((r) => r.id)
}

/** The texture file name the question names ("Its texture file is named '...'"), or null if it has none. */
export function textureName(row: Suggestion): string | null {
  const m = /Its texture file is named '([^']*)'/.exec(row.question?.instructions ?? '')
  return m && m[1] ? m[1] : null
}

/** A 404 or 502 means the Jev service is not reachable from this dashboard: it runs on the VPS. */
export function isServiceMissing(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 404 || err.status === 502)
}

/** Several per-type replies (one tab covers several question types) as one. */
export function mergeResults(replies: SuggestionsReply[]): { items: Suggestion[]; counts: Counts } {
  const counts: Counts = { pending: 0, accepted: 0, changed: 0 }
  const items: Suggestion[] = []
  for (const r of replies) {
    items.push(...r.items)
    counts.pending += r.counts.pending ?? 0
    counts.accepted += r.counts.accepted ?? 0
    counts.changed += r.counts.changed ?? 0
  }
  return { items, counts }
}
