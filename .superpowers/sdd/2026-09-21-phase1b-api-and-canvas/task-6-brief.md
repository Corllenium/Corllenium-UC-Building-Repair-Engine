### Task 6: Web scaffold + meshbuf decoder

**Files:** Create `web\package.json` (via pnpm), `web\index.html`, `web\vite.config.ts`, `web\tsconfig.json`,
`web\src\main.ts`, `web\src\App.vue`, `web\src\router.ts`, `web\src\env.d.ts`, `web\src\api\client.ts`,
`web\src\three\meshbuf.ts`, `web\src\three\meshbuf.test.ts`

**Interfaces — Produces:**
`decodeMeshbuf(buf: ArrayBuffer): DecodedMeshbuf` with `header`, `positions: Float32Array`, `uvs`, `normals`,
`triMaterial: Uint16Array`, `triFaceId: Uint32Array`, `triRegion: Int32Array`, `edgePositions: Float32Array`, `edgeClass: Uint8Array`.
`api` object: `scan(q)`, `importFile(file)`, `models()`, `versions(modelId)`, `version(id)`, `meshbuf(id): Promise<ArrayBuffer>`, `face(versionId, faceId)`.

- [ ] **Step 1: scaffold**

```
mkdir web
pnpm --dir web init
pnpm --dir web add vue vue-router three
pnpm --dir web add -D vite @vitejs/plugin-vue typescript vue-tsc vitest @types/three
```

Set `"type": "module"` and scripts `"dev": "vite"`, `"build": "vue-tsc -b && vite build"`, `"test": "vitest run"` in `web\package.json`.

`web\vite.config.ts`:

```ts
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: { environment: 'node' },
})
```

- [ ] **Step 2: failing test `web\src\three\meshbuf.test.ts`** — builds a buffer by hand in the engine's layout
  (`UCMB`, u32 version, u32 header length, space-padded JSON, 4-byte padded blocks, offsets relative to data start):

```ts
import { describe, expect, it } from 'vitest'
import { decodeMeshbuf } from './meshbuf'

function build(): ArrayBuffer {
  const pos = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0])
  const cls = new Uint8Array([1])
  const blocks = [
    { name: 'positions', dtype: 'f32', shape: [3, 3], offset: 0, nbytes: 36 },
    { name: 'edge_class', dtype: 'u8', shape: [1], offset: 36, nbytes: 1 },
  ]
  let json = JSON.stringify({ version: 1, name: 't', counts: { faces: 1, edges: 1 }, materials: [], blocks })
  while (json.length % 4) json += ' '
  const head = new TextEncoder().encode(json)
  const out = new Uint8Array(12 + head.length + 40)
  out.set([0x55, 0x43, 0x4d, 0x42])
  const dv = new DataView(out.buffer)
  dv.setUint32(4, 1, true); dv.setUint32(8, head.length, true)
  out.set(head, 12)
  out.set(new Uint8Array(pos.buffer), 12 + head.length)
  out.set(cls, 12 + head.length + 36)
  return out.buffer
}

describe('decodeMeshbuf', () => {
  it('reads header and typed blocks', () => {
    const d = decodeMeshbuf(build())
    expect(d.header.counts.faces).toBe(1)
    expect(Array.from(d.positions)).toEqual([0, 0, 0, 1, 0, 0, 0, 1, 0])
    expect(Array.from(d.edgeClass)).toEqual([1])
  })
  it('rejects a foreign file', () => {
    expect(() => decodeMeshbuf(new Uint8Array(16).buffer)).toThrow(/not a meshbuf/)
  })
})
```

Run: `pnpm --dir web test`. Expected: FAIL, cannot resolve `./meshbuf`.

- [ ] **Step 3: `web\src\three\meshbuf.ts`**

```ts
export interface MeshbufHeader {
  version: number; name: string; units?: string; unit_scale_m?: number
  origin_offset?: number[]; bbox?: { min: number[]; max: number[] }
  materials: { name: string; texture: string | null }[]
  counts: { faces: number; edges: number }
  blocks: { name: string; dtype: 'f32' | 'u16' | 'u32' | 'i32' | 'u8'; shape: number[]; offset: number; nbytes: number }[]
}
export interface DecodedMeshbuf {
  header: MeshbufHeader
  positions: Float32Array; uvs: Float32Array; normals: Float32Array
  triMaterial: Uint16Array; triFaceId: Uint32Array; triRegion: Int32Array
  edgePositions: Float32Array; edgeClass: Uint8Array
}
const CTOR = { f32: Float32Array, u16: Uint16Array, u32: Uint32Array, i32: Int32Array, u8: Uint8Array }

export function decodeMeshbuf(buf: ArrayBuffer): DecodedMeshbuf {
  const magic = new TextDecoder().decode(new Uint8Array(buf, 0, 4))
  if (magic !== 'UCMB') throw new Error('not a meshbuf')
  const dv = new DataView(buf)
  const hlen = dv.getUint32(8, true)
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 12, hlen))) as MeshbufHeader
  const start = 12 + hlen
  const get = (name: string, dtype: keyof typeof CTOR) => {
    const b = header.blocks.find(x => x.name === name)
    if (!b) return new CTOR[dtype](0)
    return new CTOR[b.dtype](buf, start + b.offset, b.shape.reduce((a, n) => a * n, 1))
  }
  return {
    header,
    positions: get('positions', 'f32') as Float32Array, uvs: get('uvs', 'f32') as Float32Array,
    normals: get('normals', 'f32') as Float32Array, triMaterial: get('tri_material', 'u16') as Uint16Array,
    triFaceId: get('tri_face_id', 'u32') as Uint32Array, triRegion: get('tri_region', 'i32') as Int32Array,
    edgePositions: get('edge_positions', 'f32') as Float32Array, edgeClass: get('edge_class', 'u8') as Uint8Array,
  }
}
```

`web\src\api\client.ts`: a `json<T>(path, init?)` helper that throws an `ApiError` carrying `status` and
`retryAfter` (from the `Retry-After` header), plus the seven wrappers listed above.
`main.ts`, `App.vue` (`<router-view/>`), `router.ts` (`/` -> ModelsView, `/models/:id` -> WorkspaceView; both views are
created as one-line stubs here and filled in Task 8), `index.html`, `tsconfig.json` (strict, `moduleResolution: "bundler"`).

- [ ] **Step 4:** `pnpm --dir web test` -> `2 passed`. `pnpm --dir web build` -> exits 0.
- [ ] **Step 5:** Add `web/node_modules/` and `web/dist/` are already covered by `.gitignore`. Commit
  `feat(web): vite + vue scaffold, api client, meshbuf decoder`.

---

