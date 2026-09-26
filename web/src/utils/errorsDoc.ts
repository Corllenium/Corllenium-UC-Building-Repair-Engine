// The Errors & fixes page's catalogue: types, constants, and pure logic.
// No Vue here — this module is plain TypeScript so its rules can be unit-tested directly.

export type Status = 'fixed' | 'partly' | 'open' | 'planned'
export type Verdict = 'error' | 'ok' | 'unsure'

export interface Example {
  image?: string
  date?: string
  words?: string
  caption?: string
  model?: string
}

export interface Kind {
  id: string
  title: string
  summary: string
  color: string // '#rrggbb'
  models: Record<string, { status: Status; count: string }> // keyed by model id
  what: string
  find: string[]
  why: string
  why_note?: string
  unity: string[]
  solution: string[]
  never?: string[]
  done: string[]
  remain: string
  engine_files: string[]
  examples: Example[]
  sources: string[]
}

export interface EngineMistake {
  id: string
  title: string
  what_happened: string
  how_caught: string
  fix: string
  models: string[]
  engine_files: string[]
  commits?: string[]
  examples: Example[]
}

export interface ModelCard {
  id: string
  name: string
  role: string
  skp?: string
  numbers: Record<string, number | number[]>
  source: string
}

export interface Catalogue {
  built_from: { commit: string; date: string }
  origin: string[] // intro paragraphs
  models: ModelCard[]
  kinds: Kind[]
  engine_mistakes: EngineMistake[]
  other_screenshots: Example[]
}

export interface DocFilter {
  model: string | null
  engine: string | null
}

export interface VerdictEntry {
  verdict: Verdict
  note: string
  at: string
}

export interface Validation {
  version: 1
  verdicts: Record<string, Record<string, VerdictEntry>> // kind id -> model id -> entry
}

export const ENGINE_FILES: string[] = [
  'vis/exposure.py',
  'fixes/remove.py',
  'fixes/solidify.py',
  'fixes/merge.py',
  'fixes/orient.py',
  'fixes/overlap.py',
  'detectors/fragments.py',
  'detectors/folds.py',
  'guard/compare.py',
  'guard/piece_rays.py',
  'io/skp_writer.py',
  'topo/adjacency.py',
  'topo/planes.py',
]

export const STATUS_LABEL: Record<Status, string> = {
  fixed: 'Fixed',
  partly: 'Partly fixed',
  open: 'Open',
  planned: 'Planned, not fixed yet',
}

export const VERDICTS: { id: Verdict; label: string }[] = [
  { id: 'error', label: 'Error, must fix' },
  { id: 'ok', label: 'OK for this model' },
  { id: 'unsure', label: 'Not sure' },
]

export const IMAGE_NAME = /^[A-Za-z0-9_.-]+\.(png|webp|jpg)$/

export const WINDOW_HEADER = 48 // px of the floating window's title bar that must stay on screen

export function engineStem(file: string): string {
  const base = file.split('/').pop() ?? file
  return base.replace(/\.py$/, '')
}

export function statusLabel(s: Status): string {
  return STATUS_LABEL[s]
}

export function imageUrl(name: string): string {
  return '/api/docs/images/' + encodeURIComponent(name)
}

export function filterKinds(kinds: Kind[], f: DocFilter): Kind[] {
  return kinds.filter(k =>
    (f.model === null || Object.prototype.hasOwnProperty.call(k.models, f.model)) &&
    (f.engine === null || k.engine_files.includes(f.engine))
  )
}

export function filterMistakes(ms: EngineMistake[], f: DocFilter): EngineMistake[] {
  return ms.filter(m =>
    (f.model === null || m.models.includes(f.model)) &&
    (f.engine === null || m.engine_files.includes(f.engine))
  )
}

export function filterChoices(cat: Catalogue): { models: { id: string; label: string }[]; engineFiles: string[] } {
  const models = cat.models.map(m => ({ id: m.id, label: `${m.id} · ${m.name}` }))

  const used = new Set<string>()
  for (const k of cat.kinds) {
    for (const f of k.engine_files) used.add(f)
  }
  for (const m of cat.engine_mistakes) {
    for (const f of m.engine_files) used.add(f)
  }
  const engineFiles = ENGINE_FILES.filter(f => used.has(f))

  return { models, engineFiles }
}

export function filterFromQuery(q: Record<string, unknown>, cat: Catalogue): DocFilter {
  const first = (v: unknown): unknown => (Array.isArray(v) ? v[0] : v)
  const modelRaw = first(q.model)
  const engineRaw = first(q.engine)
  const choices = filterChoices(cat)

  const model = typeof modelRaw === 'string' && choices.models.some(m => m.id === modelRaw) ? modelRaw : null
  const engine = typeof engineRaw === 'string'
    ? choices.engineFiles.find(f => engineStem(f) === engineRaw) ?? null
    : null

  return { model, engine }
}

export function openFromQuery(q: Record<string, unknown>, cat: Catalogue): string | null {
  const open = q.open
  if (typeof open !== 'string') return null
  const isKind = cat.kinds.some(k => k.id === open)
  const isMistake = cat.engine_mistakes.some(m => m.id === open)
  return isKind || isMistake ? open : null
}

export function filterToQuery(f: DocFilter, open: string | null): Record<string, string> {
  const q: Record<string, string> = {}
  if (f.model !== null) q.model = f.model
  if (f.engine !== null) q.engine = engineStem(f.engine)
  if (open !== null) q.open = open
  return q
}

export function clampWindow(x: number, y: number, w: number, vw: number, vh: number): { x: number; y: number } {
  const clampedX = Math.min(Math.max(x, 0), Math.max(0, vw - w))
  const clampedY = Math.min(Math.max(y, 0), Math.max(0, vh - WINDOW_HEADER))
  return { x: clampedX, y: clampedY }
}

export function verdictOf(v: Validation | null, kindId: string, modelId: string): VerdictEntry | null {
  if (!v) return null
  const forKind = v.verdicts[kindId]
  if (!forKind) return null
  return forKind[modelId] ?? null
}

export function validationSummary(
  cat: Catalogue,
  v: Validation | null
): { pairs: number; validated: number; error: number; ok: number; unsure: number } {
  let pairs = 0
  let validated = 0
  let error = 0
  let ok = 0
  let unsure = 0

  for (const k of cat.kinds) {
    for (const modelId of Object.keys(k.models)) {
      pairs++
      const entry = verdictOf(v, k.id, modelId)
      if (entry) {
        validated++
        if (entry.verdict === 'error') error++
        else if (entry.verdict === 'ok') ok++
        else if (entry.verdict === 'unsure') unsure++
      }
    }
  }

  return { pairs, validated, error, ok, unsure }
}

function isBlank(value: string): boolean {
  return value.trim() === ''
}

function hasNoSteps(values: string[]): boolean {
  return !values.some(v => v.trim() !== '')
}

function checkImages(problems: string[], label: string, examples: Example[]): void {
  for (const ex of examples) {
    if (ex.image !== undefined && !IMAGE_NAME.test(ex.image)) {
      problems.push(`${label}: bad image name "${ex.image}"`)
    }
  }
}

export function validateCatalogue(cat: Catalogue): string[] {
  const problems: string[] = []
  const seenIds = new Set<string>()
  const modelIds = new Set(cat.models.map(m => m.id))

  for (const k of cat.kinds) {
    const id = k.id

    // 1. duplicate id
    if (seenIds.has(id)) problems.push(`${id}: duplicate id`)
    else seenIds.add(id)

    // 2. empty text fields
    const textFields: [string, string][] = [
      ['summary', k.summary],
      ['what', k.what],
      ['why', k.why],
      ['remain', k.remain],
    ]
    for (const [field, value] of textFields) {
      if (isBlank(value)) problems.push(`${id}: "${field}" is empty`)
    }

    // 3. step lists with no non-empty item
    const stepFields: [string, string[]][] = [
      ['find', k.find],
      ['unity', k.unity],
      ['solution', k.solution],
      ['done', k.done],
    ]
    for (const [field, values] of stepFields) {
      if (hasNoSteps(values)) problems.push(`${id}: "${field}" has no steps`)
    }

    // 4. colour
    if (!/^#[0-9a-fA-F]{6}$/.test(k.color)) problems.push(`${id}: bad colour "${k.color}"`)

    // 5. models: unknown model id, then unknown status
    for (const modelId of Object.keys(k.models)) {
      if (!modelIds.has(modelId)) problems.push(`${id}: unknown model "${modelId}"`)
      const status = k.models[modelId].status
      if (!Object.prototype.hasOwnProperty.call(STATUS_LABEL, status)) {
        problems.push(`${id}: unknown status "${status}"`)
      }
    }

    // 6. engine files
    for (const file of k.engine_files) {
      if (!ENGINE_FILES.includes(file)) problems.push(`${id}: unknown engine file "${file}"`)
    }

    // 7. example images
    checkImages(problems, id, k.examples)
  }

  for (const m of cat.engine_mistakes) {
    const id = m.id

    // 1. duplicate id
    if (seenIds.has(id)) problems.push(`${id}: duplicate id`)
    else seenIds.add(id)

    // 2. empty text fields
    const textFields: [string, string][] = [
      ['what_happened', m.what_happened],
      ['how_caught', m.how_caught],
      ['fix', m.fix],
    ]
    for (const [field, value] of textFields) {
      if (isBlank(value)) problems.push(`${id}: "${field}" is empty`)
    }

    // 3. models
    for (const modelId of m.models) {
      if (!modelIds.has(modelId)) problems.push(`${id}: unknown model "${modelId}"`)
    }

    // 4. engine files
    for (const file of m.engine_files) {
      if (!ENGINE_FILES.includes(file)) problems.push(`${id}: unknown engine file "${file}"`)
    }

    // 5. example images
    checkImages(problems, id, m.examples)
  }

  // Last: other_screenshots images
  checkImages(problems, 'other_screenshots', cat.other_screenshots)

  return problems
}
