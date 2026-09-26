### Task 8: the filter logic, as pure functions

**Files:**
- Create: `web/src/utils/errorLayers.ts`
- Test: `web/src/utils/errorLayers.test.ts`

**Interfaces:**
- Produces (exact names):

```ts
export type ErrorKind = 'flicker_diff' | 'flicker_same' | 'reversed' | 'hidden' | 'loose' | 'open_edges' | 'cracks' | 'facade'
export interface ErrorSpot { label: string; centre: [number, number, number]; size: number; value: number; faces: number[] }
export interface ErrorsFile {
  version: number; n_faces: number
  counts: Record<Exclude<ErrorKind, 'facade'>, number>
  faces: Record<'flicker_diff' | 'flicker_same' | 'reversed' | 'hidden' | 'loose', number[]>
  layers: { facade: number[] }; layer_counts: { facade: number }   // Task 14
  open_edges: number[][]; cracks: number[][]
  flicker_pairs: [number, number, number, boolean][]
  spots: Record<ErrorKind, ErrorSpot[]>
}
export interface ErrorFilter { enabled: Record<ErrorKind, boolean>; isolate: boolean; blink: boolean }
export const ERROR_KINDS: { kind: ErrorKind; label: string; color: number; draw: 'faces' | 'lines' | 'points' }[]
export const FACE_KINDS: ErrorKind[]  // the 'faces' ones, in priority order; 'facade' last
export function faceList(file: ErrorsFile, kind: FaceKind): number[]
export function countOf(file: ErrorsFile, kind: ErrorKind): number
export function defaultFilter(): ErrorFilter   // every kind on except 'facade'
export function overlayFaces(file: ErrorsFile, filter: ErrorFilter): { faces: number[]; colors: Float32Array }
export function blinkColors(file: ErrorsFile, faces: number[], triMaterial: ArrayLike<number>, phase: 0 | 1): Float32Array
export function partnersOf(file: ErrorsFile, face: number): { face: number; shared: number; opposite: boolean }[]
export function kindsOf(file: ErrorsFile, face: number): ErrorKind[]
export function openEdgeSegments(file: ErrorsFile, origin: number[]): Float32Array
export function crackPoints(file: ErrorsFile, origin: number[]): Float32Array
export function toViewer(p: number[], origin: number[]): [number, number, number]
export function materialColor(index: number): number
```

- [ ] **Step 1: Write the failing tests** (`web/src/utils/errorLayers.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import {
  ERROR_KINDS, FACE_KINDS, defaultFilter, overlayFaces, blinkColors, partnersOf, kindsOf,
  openEdgeSegments, crackPoints, toViewer, materialColor, countOf, type ErrorsFile,
} from './errorLayers'

const file: ErrorsFile = {
  version: 1, n_faces: 6,
  counts: { flicker_diff: 2, flicker_same: 0, reversed: 1, hidden: 2, loose: 0, open_edges: 1, cracks: 1 },
  faces: { flicker_diff: [0, 1], flicker_same: [], reversed: [1], hidden: [4, 5], loose: [] },
  layers: { facade: [0, 3] }, layer_counts: { facade: 2 },
  open_edges: [[10, 0, 0, 20, 0, 0]], cracks: [[15, 5, 0]],
  flicker_pairs: [[0, 1, 100, true]],
  spots: { flicker_diff: [], flicker_same: [], reversed: [], hidden: [], loose: [], open_edges: [], cracks: [], facade: [] },
}

describe('errorLayers', () => {
  it('lists the seven error kinds and the facade layer in priority order with the spec colours', () => {
    expect(ERROR_KINDS.map(k => k.kind)).toEqual(
      ['flicker_diff', 'flicker_same', 'reversed', 'hidden', 'loose', 'open_edges', 'cracks', 'facade'])
    expect(ERROR_KINDS[0].color).toBe(0xd8282f)
    expect(FACE_KINDS).toEqual(['flicker_diff', 'flicker_same', 'reversed', 'hidden', 'loose', 'facade'])
  })

  it('draws the facade in teal only when asked, and never over an error colour', () => {
    const f = defaultFilter()
    expect(f.enabled.facade).toBe(false)
    f.enabled.facade = true
    const { faces, colors } = overlayFaces(file, f)
    expect(faces).toEqual([0, 1, 3, 4, 5])
    // face 0 is flicker_diff AND facade: red wins; face 3 (slot 2) is facade only: teal
    expect(Array.from(colors.slice(0, 3)).map(v => Math.round(v * 255))).toEqual([0xd8, 0x28, 0x2f])
    expect(Array.from(colors.slice(18, 21)).map(v => Math.round(v * 255))).toEqual([0x0d, 0x94, 0x88])
  })

  it('counts errors from counts and the facade from layer_counts', () => {
    expect(countOf(file, 'reversed')).toBe(1)
    expect(countOf(file, 'facade')).toBe(2)
  })

  it('draws only the enabled kinds, a face in two kinds in the first one', () => {
    const f = defaultFilter()
    const { faces, colors } = overlayFaces(file, f)
    expect(faces).toEqual([0, 1, 4, 5])
    // face 1 is flicker_diff AND reversed: red wins
    expect(Array.from(colors.slice(9, 12)).map(v => Math.round(v * 255))).toEqual([0xd8, 0x28, 0x2f])
    f.enabled.flicker_diff = false
    expect(overlayFaces(file, f).faces).toEqual([1, 4, 5])
    expect(Array.from(overlayFaces(file, f).colors.slice(0, 3)).map(v => Math.round(v * 255))).toEqual([0x96, 0x50, 0xff])
  })

  it('blinks a flicker face between its own material and its partner s', () => {
    const tm = [3, 7, 0, 0, 0, 0]
    const a = blinkColors(file, [0, 1], tm, 0)
    const b = blinkColors(file, [0, 1], tm, 1)
    expect(Array.from(a.slice(0, 3))).toEqual(Array.from(b.slice(9, 12)))  // face 0 now = face 1 then
    expect(Array.from(a.slice(0, 3))).not.toEqual(Array.from(b.slice(0, 3)))
  })

  it('names a face s partners and kinds', () => {
    expect(partnersOf(file, 1)).toEqual([{ face: 0, shared: 100, opposite: true }])
    expect(kindsOf(file, 1)).toEqual(['flicker_diff', 'reversed'])
    expect(kindsOf(file, 2)).toEqual([])
    expect(kindsOf(file, 3)).toEqual(['facade'])
  })

  it('moves lines and points into the viewer s frame', () => {
    const origin = [10, 0, 0]
    expect(Array.from(openEdgeSegments(file, origin))).toEqual([0, 0, 0, 10, 0, 0])
    expect(Array.from(crackPoints(file, origin))).toEqual([5, 5, 0])
    expect(toViewer([11, 2, 3], origin)).toEqual([1, 2, 3])
  })

  it('gives different materials different colours', () => {
    expect(materialColor(0)).not.toBe(materialColor(1))
    expect(materialColor(12)).toBe(materialColor(0))
  })
})
```

- [ ] **Step 2: Run and see them fail**

Run: `pnpm --dir web exec vitest run src/utils/errorLayers.test.ts`
Expected: FAIL (cannot find module `./errorLayers`).

- [ ] **Step 3: Implement** `web/src/utils/errorLayers.ts`:

```ts
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
  const out: { face: number; shared: number; opposite: boolean }[] = []
  for (const [i, j, shared, opposite] of file.flicker_pairs) {
    if (i === face) out.push({ face: j, shared, opposite })
    else if (j === face) out.push({ face: i, shared, opposite })
  }
  return out
}

export function blinkColors(file: ErrorsFile, faces: number[], triMaterial: ArrayLike<number>, phase: 0 | 1): Float32Array {
  const colors = new Float32Array(faces.length * 9)
  faces.forEach((f, slot) => {
    const partner = partnersOf(file, f)[0]
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
```

- [ ] **Step 4: Run and see them pass**

Run: `pnpm --dir web exec vitest run src/utils/errorLayers.test.ts`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/utils/errorLayers.ts web/src/utils/errorLayers.test.ts
git commit -m "feat(web): the error filter's logic -- kinds, colours, blink, partners, lines and points" -m "Pure functions over the errors file, so every rule is unit-tested and the viewport only draws what they return." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

