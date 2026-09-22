export interface SourceFile {
  file: string
  tri_count?: number
  size_bytes?: number
}

export interface ModelVersion {
  id: number
  model_id: number
  kind: 'snapshot' | 'preview' | 'fixed'
  sha256: string
  asset_sha256?: string
  tri_count: number
  created_at: string
}

export interface Model {
  id: number
  name: string
  source_file: string
  created_at: string
  versions: ModelVersion[]
}

export interface FixProfile {
  n_dirs?: number
  slit_threshold?: number
  accept_slit?: boolean
  flat_texture_std?: number
}

export interface FixRun {
  id: number
  version_id: number
  fixed_version_id?: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  config?: any
  report_json?: {
    name: string
    tris_before: number
    tris_after: number
    passed: boolean
    n_removed_hidden: number
    n_restored_by_guard: number
    n_flipped: number
    n_zero_area_dropped: number
    one_sided_holes_before: number
    one_sided_holes_after: number
    guard_passed: boolean
  }
  error?: string
  created_at: string
}

const API_BASE = '/api'

export async function fetchSourceFiles(): Promise<SourceFile[]> {
  const res = await fetch(`${API_BASE}/source/files`)
  if (!res.ok) throw new Error(`Failed to fetch source files: ${res.statusText}`)
  return res.json()
}

export async function fetchModels(): Promise<Model[]> {
  const res = await fetch(`${API_BASE}/models`)
  if (!res.ok) throw new Error(`Failed to fetch models: ${res.statusText}`)
  return res.json()
}

export async function fetchModel(id: number): Promise<Model> {
  const res = await fetch(`${API_BASE}/models/${id}`)
  if (!res.ok) throw new Error(`Failed to fetch model ${id}: ${res.statusText}`)
  return res.json()
}

export async function importModel(fileName: string): Promise<Model> {
  const res = await fetch(`${API_BASE}/models/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file: fileName }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Import failed')
  }
  return res.json()
}

export async function fetchMeshbuf(versionId: number): Promise<ArrayBuffer> {
  const res = await fetch(`${API_BASE}/versions/${versionId}/meshbuf`)
  if (!res.ok) throw new Error(`Failed to fetch meshbuf: ${res.statusText}`)
  return res.arrayBuffer()
}

export async function runFix(versionId: number, profile?: FixProfile): Promise<FixRun> {
  const res = await fetch(`${API_BASE}/versions/${versionId}/fix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile: profile || {} }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Fix failed')
  }
  return res.json()
}

export async function fetchRun(runId: number): Promise<FixRun> {
  const res = await fetch(`${API_BASE}/runs/${runId}`)
  if (!res.ok) throw new Error(`Failed to fetch run: ${res.statusText}`)
  return res.json()
}

export function getGuardImageUrl(runId: number, view: string): string {
  return `${API_BASE}/runs/${runId}/guard/${view}`
}
