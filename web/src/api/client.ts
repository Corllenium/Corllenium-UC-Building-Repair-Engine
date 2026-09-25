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
  report_json?: any
  guard_views?: string[]
  skp?: any
  error?: string
  created_at: string
}

export class ApiError extends Error {
  status: number
  retryAfter?: number

  constructor(message: string, status: number, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

const API_BASE = '/api'

async function checkResponse(res: Response, fallbackMsg: string): Promise<Response> {
  if (!res.ok) {
    let detail = fallbackMsg
    try {
      const data = await res.json()
      if (data?.detail) {
        detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      }
    } catch {
      detail = `${fallbackMsg}: ${res.statusText}`
    }
    const retryHeader = res.headers.get('Retry-After')
    const retryAfter = retryHeader ? parseInt(retryHeader, 10) : undefined
    throw new ApiError(detail, res.status, retryAfter)
  }
  return res
}

export async function fetchSourceFiles(): Promise<SourceFile[]> {
  const res = await checkResponse(await fetch(`${API_BASE}/source/files`), 'Failed to fetch source files')
  return res.json()
}

export async function fetchModels(): Promise<Model[]> {
  const res = await checkResponse(await fetch(`${API_BASE}/models`), 'Failed to fetch models')
  return res.json()
}

export async function rescanModels(): Promise<Model[]> {
  const res = await checkResponse(
    await fetch(`${API_BASE}/models/rescan`, { method: 'POST' }),
    'Rescan failed'
  )
  return res.json()
}

export async function fetchModel(id: number): Promise<Model> {
  const res = await checkResponse(await fetch(`${API_BASE}/models/${id}`), `Failed to fetch model ${id}`)
  return res.json()
}

export async function importModel(fileName: string): Promise<Model> {
  const res = await checkResponse(
    await fetch(`${API_BASE}/models/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: fileName }),
    }),
    'Import failed'
  )
  return res.json()
}

export async function fetchMeshbuf(versionId: number): Promise<ArrayBuffer> {
  const res = await checkResponse(
    await fetch(`${API_BASE}/versions/${versionId}/meshbuf`),
    'Failed to fetch meshbuf'
  )
  return res.arrayBuffer()
}

export async function runFix(versionId: number, profile?: FixProfile): Promise<FixRun> {
  const res = await checkResponse(
    await fetch(`${API_BASE}/versions/${versionId}/fix`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: profile || {} }),
    }),
    'Fix failed'
  )
  return res.json()
}

export async function fetchRun(runId: number): Promise<FixRun> {
  const res = await checkResponse(await fetch(`${API_BASE}/runs/${runId}`), 'Failed to fetch run')
  return res.json()
}

export async function fetchVersionRun(versionId: number): Promise<FixRun> {
  const res = await checkResponse(await fetch(`${API_BASE}/versions/${versionId}/run`), 'Failed to fetch version run')
  return res.json()
}


export function getGuardImageUrl(runId: number, view: string): string {
  return `${API_BASE}/runs/${runId}/guard/${view}`
}

export interface SourceFaceInfo {
  face_id: number
  line: number
}

export interface FaceDetails {
  face_id: number
  line: number
  material?: string | null
  vertices: number[][]
  source_faces?: SourceFaceInfo[]
}

export async function fetchFace(versionId: number, faceId: number): Promise<FaceDetails> {
  const res = await checkResponse(
    await fetch(`${API_BASE}/versions/${versionId}/faces/${faceId}`),
    'Failed to fetch face details'
  )
  return res.json()
}

