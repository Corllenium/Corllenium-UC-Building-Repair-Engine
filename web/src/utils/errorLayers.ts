export type ErrorKind = 'flicker_diff' | 'flicker_same' | 'reversed' | 'hidden' | 'loose' | 'open_edges' | 'cracks' | 'facade'
type FaceKind = 'flicker_diff' | 'flicker_same' | 'reversed' | 'hidden' | 'loose' | 'facade'

export interface ErrorSpot { label: string; centre: [number, number, number]; size: number; value: number; faces: number[] }
export interface ErrorsFile {
  version: number
  n_faces: number
  counts: Record<Exclude<ErrorKind, 'facade'>, number>
  faces: Record<Exclude<FaceKind, 'facade'>, number[]>
  layers: { facade: number[] }          // Task 14: every face seen from outside -- not an error
  layer_counts: { facade: number }
  open_edges: number[][]
  cracks: number[][]
  flicker_pairs: [number, number, number, boolean][]
  spots: Record<ErrorKind, ErrorSpot[]>
}
export interface ErrorFilter { enabled: Record<ErrorKind, boolean>; isolate: boolean; blink: boolean }

export const ERROR_KINDS: { kind: ErrorKind; label: string; color: number; draw: 'faces' | 'lines' | 'points' }[] = [
  { kind: 'flicker_diff', label: 'Flicker: texture on texture', color: 0xd8282f, draw: 'faces' },
  { kind: 'flicker_same', label: 'Flicker: same material', color: 0xf08c00, draw: 'faces' },
  { kind: 'reversed', label: 'Reversed / back faces', color: 0x9650ff, draw: 'faces' },
  { kind: 'hidden', label: 'Hidden inside faces', color: 0x1f5bff, draw: 'faces' },
  { kind: 'loose', label: 'Zero-area and stray bits', color: 0xe0199b, draw: 'faces' },
  { kind: 'open_edges', label: 'Open edges', color: 0x16a34a, draw: 'lines' },
  { kind: 'cracks', label: 'Cracks (T-junction points)', color: 0x00b4d8, draw: 'points' },
  { kind: 'facade', label: 'Facade (seen from outside)', color: 0x0d9488, draw: 'faces' },
]
export const FACE_KINDS = ERROR_KINDS.filter(k => k.draw === 'faces').map(k => k.kind) as FaceKind[]

/** A face kind's faces: the errors' own lists, or the facade layer (Task 14). */
export function faceList(file: ErrorsFile, kind: FaceKind): number[] {
  return kind === 'facade' ? (file.layers?.facade ?? []) : file.faces[kind]
}

/** How many of a kind the file holds: faces, open edges, crack points or facade faces. */
export function countOf(file: ErrorsFile, kind: ErrorKind): number {
  return kind === 'facade' ? (file.layer_counts?.facade ?? 0) : file.counts[kind]
}

// 12 distinct hues for blinking materials against each other
const MATERIAL_PALETTE = [0xe6194b, 0x3cb44b, 0xffe119, 0x4363d8, 0xf58231, 0x911eb4,
  0x46f0f0, 0xf032e6, 0xbcf60c, 0xfabebe, 0x008080, 0x9a6324]

export function materialColor(index: number): number {
  return MATERIAL_PALETTE[((index % MATERIAL_PALETTE.length) + MATERIAL_PALETTE.length) % MATERIAL_PALETTE.length]
}

export function defaultFilter(): ErrorFilter {
  const enabled = Object.fromEntries(ERROR_KINDS.map(k => [k.kind, k.kind !== 'facade'])) as Record<ErrorKind, boolean>
  return { enabled, isolate: false, blink: false }
}

// Cache partner indices per file object to avoid O(pairs) scan per face
const partnerIndexCache = new WeakMap<ErrorsFile, Map<number, { face: number; shared: number; opposite: boolean }[]>>()

export function partnerIndex(file: ErrorsFile): Map<number, { face: number; shared: number; opposite: boolean }[]> {
  let cached = partnerIndexCache.get(file)
  if (!cached) {
    cached = new Map<number, { face: number; shared: number; opposite: boolean }[]>()
    for (const [i, j, shared, opposite] of file.flicker_pairs) {
      // Add i -> j
      if (!cached.has(i)) cached.set(i, [])
      cached.get(i)!.push({ face: j, shared, opposite })
      // Add j -> i (with opposite flipped)
      if (!cached.has(j)) cached.set(j, [])
      cached.get(j)!.push({ face: i, shared, opposite })
    }
    partnerIndexCache.set(file, cached)
  }
  return cached
}

function rgb(color: number): [number, number, number] {
  return [((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255]
}

function fill(colors: Float32Array, slot: number, color: number) {
  const [r, g, b] = rgb(color)
  for (let v = 0; v < 3; v++) colors.set([r, g, b], slot * 9 + v * 3)
}

export function overlayFaces(file: ErrorsFile, filter: ErrorFilter): { faces: number[]; colors: Float32Array } {
  const colorOf = new Map<number, number>()
  for (const k of FACE_KINDS) {
    if (!filter.enabled[k]) continue
    const color = ERROR_KINDS.find(e => e.kind === k)!.color
    for (const f of faceList(file, k)) if (!colorOf.has(f)) colorOf.set(f, color)
  }
  const faces = [...colorOf.keys()].sort((a, b) => a - b)
  const colors = new Float32Array(faces.length * 9)
  faces.forEach((f, slot) => fill(colors, slot, colorOf.get(f)!))
  return { faces, colors }
}

export function partnersOf(file: ErrorsFile, face: number): { face: number; shared: number; opposite: boolean }[] {
  return partnerIndex(file).get(face) ?? []
}

export function blinkColors(file: ErrorsFile, faces: number[], triMaterial: ArrayLike<number>, phase: 0 | 1): Float32Array {
  const colors = new Float32Array(faces.length * 9)
  const partners = partnerIndex(file)
  faces.forEach((f, slot) => {
    const partner = partners.get(f)?.[0]
    const own = triMaterial[f]
    const other = partner ? triMaterial[partner.face] : own
    fill(colors, slot, materialColor(phase === 0 ? own : other))
  })
  return colors
}

export function kindsOf(file: ErrorsFile, face: number): ErrorKind[] {
  return FACE_KINDS.filter(k => faceList(file, k).includes(face))
}

export function toViewer(p: number[], origin: number[]): [number, number, number] {
  return [p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]]
}

export function openEdgeSegments(file: ErrorsFile, origin: number[]): Float32Array {
  const out = new Float32Array(file.open_edges.length * 6)
  file.open_edges.forEach((s, k) => {
    out.set(toViewer(s.slice(0, 3), origin), k * 6)
    out.set(toViewer(s.slice(3, 6), origin), k * 6 + 3)
  })
  return out
}

export function crackPoints(file: ErrorsFile, origin: number[]): Float32Array {
  const out = new Float32Array(file.cracks.length * 3)
  file.cracks.forEach((p, k) => out.set(toViewer(p, origin), k * 3))
  return out
}
