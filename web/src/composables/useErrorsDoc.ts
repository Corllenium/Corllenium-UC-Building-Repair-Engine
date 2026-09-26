// Loading the Errors catalogue and saving verdicts against it. Shared by the Errors page and the
// workspace's (i) windows. No page-specific concerns here (no route, no window ref, no banner) --
// callers get an onError callback for a failed save and decide what to do with the message.

import { ref } from 'vue'
import { validateCatalogue, type Catalogue, type Validation, type Verdict, type VerdictEntry } from '../utils/errorsDoc'

export interface SavePayload {
  kindId: string
  modelId: string
  verdict: Verdict | null
  note: string
}

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

// 422 -> the first field error's message; a string `detail` -> that string; else `HTTP <status>`.
export function errorText(status: number, body: unknown): string {
  const data = (body ?? {}) as { detail?: unknown }
  if (status === 422 && Array.isArray(data.detail) && (data.detail[0] as { msg?: string } | undefined)?.msg) {
    return (data.detail[0] as { msg: string }).msg
  }
  if (typeof data.detail === 'string') {
    return data.detail
  }
  return `HTTP ${status}`
}

export function useErrorsDoc() {
  const catalogue = ref<Catalogue | null>(null)
  const validation = ref<Validation | null>(null)
  const loadError = ref('')
  const loadProblems = ref<string[]>([])
  const validationError = ref(false)
  const loaded = ref(false)

  let inflight: Promise<void> | null = null

  // Idempotent, and safe to call from every (i) button: a call while a load is already in
  // flight reuses that same promise instead of firing a second fetch.
  function load(): Promise<void> {
    if (loaded.value) return Promise.resolve()
    if (inflight) return inflight
    inflight = doLoad().finally(() => {
      inflight = null
    })
    return inflight
  }

  async function doLoad(): Promise<void> {
    loadError.value = ''
    loadProblems.value = []
    try {
      const res = await fetch('/docs/errors.json', { cache: 'no-cache' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const contentType = res.headers.get('content-type') ?? ''
      if (!contentType.includes('json')) {
        loadError.value = 'The documentation file is missing from this build (/docs/errors.json)'
      } else {
        const parsed = (await res.json()) as Catalogue
        const problems = validateCatalogue(parsed)
        if (problems.length > 0) {
          loadError.value = `The documentation file has ${problems.length} problems:`
          loadProblems.value = problems
        } else {
          catalogue.value = parsed
        }
      }
    } catch (err) {
      loadError.value = `Could not load the documentation: ${errMsg(err)}`
    } finally {
      loaded.value = true
    }

    try {
      const res = await fetch('/api/docs/validation')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      validation.value = (await res.json()) as Validation
    } catch {
      validationError.value = true
    }
  }

  const saveChains = new Map<string, Promise<void>>()

  // Saves for the same kind/model are chained so a note-blur and a verdict click fired close
  // together always reach the server in the order they were made, never racing.
  function saveVerdict(payload: SavePayload, onError?: (message: string) => void): Promise<void> {
    const key = `${payload.kindId}/${payload.modelId}`
    const chained = (saveChains.get(key) ?? Promise.resolve()).then(() => doSaveVerdict(payload, onError))
    saveChains.set(key, chained)
    return chained
  }

  async function doSaveVerdict(payload: SavePayload, onError?: (message: string) => void): Promise<void> {
    try {
      const res = await fetch(
        `/api/docs/validation/${encodeURIComponent(payload.kindId)}/${encodeURIComponent(payload.modelId)}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ verdict: payload.verdict, note: payload.note }),
        }
      )
      if (!res.ok) {
        let body: unknown = {}
        try {
          body = await res.json()
        } catch {
          // keep default body
        }
        throw new Error(errorText(res.status, body))
      }
      const data = (await res.json()) as { kind: string; model: string; entry: VerdictEntry | null }
      if (!validation.value) validation.value = { version: 1, verdicts: {} }
      if (data.entry) {
        if (!validation.value.verdicts[data.kind]) validation.value.verdicts[data.kind] = {}
        validation.value.verdicts[data.kind][data.model] = data.entry
      } else if (validation.value.verdicts[data.kind]) {
        delete validation.value.verdicts[data.kind][data.model]
        if (Object.keys(validation.value.verdicts[data.kind]).length === 0) {
          delete validation.value.verdicts[data.kind]
        }
      }
    } catch (err) {
      onError?.(errMsg(err))
    }
  }

  return {
    catalogue,
    validation,
    loadError,
    loadProblems,
    validationError,
    loaded,
    load,
    saveVerdict,
  }
}
