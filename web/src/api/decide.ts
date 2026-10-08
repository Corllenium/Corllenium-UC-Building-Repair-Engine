// Client for the uc-fixer-decide service (runs on the VPS, reached through /api/decide/*).
// Every failure is thrown as the existing ApiError, so a view can read `.status`.
import { checkResponse } from './client'
import type { DecideHealth, ReviewBody, SuggestionsReply, Suggestion } from '../utils/jevReview'

const DECIDE_BASE = '/api/decide'

export interface SuggestionParams {
  status?: string
  type?: string
  min_conf?: number
  q?: string
  limit?: number
  offset?: number
}

export async function fetchSuggestions(params: SuggestionParams = {}): Promise<SuggestionsReply> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (typeof value === 'number' && !Number.isFinite(value)) continue
    query.set(key, String(value))
  }
  const qs = query.toString()
  const res = await checkResponse(
    await fetch(`${DECIDE_BASE}/suggestions${qs ? `?${qs}` : ''}`),
    'Failed to fetch suggestions'
  )
  return res.json()
}

/** Send `{accept: true}` or `{answer: value}`, never both. The value is the RAW one: a bool, a label, an int. */
export async function reviewSuggestion(id: number, body: ReviewBody): Promise<Suggestion> {
  const res = await checkResponse(
    await fetch(`${DECIDE_BASE}/review/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
    'Review failed'
  )
  return res.json()
}

export async function reaskSuggestion(id: number): Promise<Suggestion> {
  const res = await checkResponse(
    // A JSON body is required: the service answers 422 to a post without one, so a form cannot trigger a re-ask.
    await fetch(`${DECIDE_BASE}/reask/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }),
    'Re-ask failed'
  )
  return res.json()
}

export async function fetchHealth(): Promise<DecideHealth> {
  const res = await checkResponse(await fetch(`${DECIDE_BASE}/health`), 'Failed to fetch Jev health')
  return res.json()
}
