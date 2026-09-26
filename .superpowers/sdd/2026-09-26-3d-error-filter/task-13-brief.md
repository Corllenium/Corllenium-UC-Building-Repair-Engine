### Task 13: real textures in the 3D viewer (added 2026-09-26, owner: "where's the texture, we need to show it in the model")

The viewer draws each material as a grey shade (`Viewport.loadModel`, vertex colours from
`triMaterial`). Everything needed for textures is already served:
- The meshbuf has UVs: CHTM 5th floor has 61,797 rows, 3 per face.
- Its header lists each material's texture: `{"name": "minecraft_quartz_block_side_-1", "texture": "tex/minecraft_quartz_block_side_-1.png"}`.
- `GET /api/versions/{id}/textures/{file name}` returns the PNG. It is looked up by FILE name:
  `…/textures/minecraft_quartz_block_side_-1.png` → 200, while the material name → 404 (measured).

With textures, coincident faces z-fight as they do in Unity, so the flicker is visible as it really
is. The error filter's colours then draw on top.

**Files:**
- Create: `web/src/utils/materialGroups.ts`, `web/src/utils/materialGroups.test.ts`
- Modify: `web/src/three/Viewport.ts`, `web/src/composables/useLayers.ts` (and its test), `web/src/views/WorkspaceView.vue`

**Interfaces:**
- `groupByMaterial(triMaterial: ArrayLike<number>): { order: Uint32Array; groups: { start: number; count: number; material: number }[] }`
  - `order[k]` is the face drawn at slot k: faces sorted by material, and by face number within a material.
  - `start` and `count` are in VERTICES (3 per face), as three.js `addGroup` wants for non-indexed geometry.
- `textureUrl(versionId: number, texture: string | null): string | null`
- `Viewport.loadModel(data, versionId?: number)` and `Viewport.setTextured(on: boolean)`.
- A new layer `textures`, default `true`, hotkey `u`.

- [ ] **Step 1: Write the failing tests** (`web/src/utils/materialGroups.test.ts`)

```ts
import { describe, it, expect } from 'vitest'
import { groupByMaterial, textureUrl } from './materialGroups'

describe('groupByMaterial', () => {
  it('sorts faces by material into one group per material, keeping face order within a material', () => {
    const { order, groups } = groupByMaterial([2, 0, 2, 1, 0])
    expect(Array.from(order)).toEqual([1, 4, 3, 0, 2])
    expect(groups).toEqual([
      { start: 0, count: 6, material: 0 },
      { start: 6, count: 3, material: 1 },
      { start: 9, count: 6, material: 2 },
    ])
  })

  it('handles an empty model', () => {
    const { order, groups } = groupByMaterial([])
    expect(order.length).toBe(0)
    expect(groups).toEqual([])
  })
})

describe('textureUrl', () => {
  it('asks the API for a texture by its file name', () => {
    expect(textureUrl(6, 'tex/minecraft_quartz_block_side_-1.png'))
      .toBe('/api/versions/6/textures/minecraft_quartz_block_side_-1.png')
    expect(textureUrl(6, null)).toBeNull()
  })
})
```

- [ ] **Step 2: Run them and see them fail**

Run: `pnpm --dir web exec vitest run src/utils/materialGroups.test.ts`
Expected: FAIL (cannot find module).

- [ ] **Step 3: Implement** `web/src/utils/materialGroups.ts`

```ts
export interface MaterialGroups {
  order: Uint32Array
  groups: { start: number; count: number; material: number }[]
}

/** Faces sorted by material so each material draws as one group; order[k] is the face drawn at slot k. */
export function groupByMaterial(triMaterial: ArrayLike<number>): MaterialGroups {
  const n = triMaterial.length
  const order = new Uint32Array(n)
  for (let i = 0; i < n; i++) order[i] = i
  order.sort((a, b) => triMaterial[a] - triMaterial[b] || a - b)
  const groups: MaterialGroups['groups'] = []
  let start = 0
  for (let k = 1; k <= n; k++) {
    if (k === n || triMaterial[order[k]] !== triMaterial[order[start]]) {
      groups.push({ start: start * 3, count: (k - start) * 3, material: triMaterial[order[start]] })
      start = k
    }
  }
  return { order, groups }
}

/** The API serves a version's textures by their FILE name, e.g. `…/textures/minecraft_quartz_block_side_-1.png`. */
export function textureUrl(versionId: number, texture: string | null): string | null {
  if (!texture) return null
  const name = texture.split('/').pop()!
  return `/api/versions/${versionId}/textures/${encodeURIComponent(name)}`
}
```

- [ ] **Step 4: Run and see them pass**

Run: `pnpm --dir web exec vitest run src/utils/materialGroups.test.ts`
Expected: 3 passed.

- [ ] **Step 5: The textured facade in `web/src/three/Viewport.ts`**
  - Add `textured?: THREE.Mesh` to the `parts` type, and the fields `private faceOrder?: Uint32Array` and
    `private texturedOn = true`.
  - Import `groupByMaterial, textureUrl` from `../utils/materialGroups`.
  - Change the signature to `loadModel(data: DecodedMeshbuf, versionId?: number)`. At the end of
    `loadModel` (before the camera fit), add:

```ts
    if (versionId !== undefined && data.header.materials.some(m => m.texture)) {
      const { order, groups } = groupByMaterial(data.triMaterial)
      const n = order.length
      const pos = new Float32Array(n * 9), nor = new Float32Array(n * 9), uv = new Float32Array(n * 6)
      for (let k = 0; k < n; k++) {
        const f = order[k]
        pos.set(data.positions.subarray(f * 9, f * 9 + 9), k * 9)
        nor.set(data.normals.subarray(f * 9, f * 9 + 9), k * 9)
        uv.set(data.uvs.subarray(f * 6, f * 6 + 6), k * 6)
      }
      const tgeom = new THREE.BufferGeometry()
      tgeom.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      tgeom.setAttribute('normal', new THREE.BufferAttribute(nor, 3))
      tgeom.setAttribute('uv', new THREE.BufferAttribute(uv, 2))
      const nMat = data.header.materials.length
      const loader = new THREE.TextureLoader()
      const mats: THREE.Material[] = data.header.materials.map((m, i) => {
        const url = textureUrl(versionId, m.texture)
        const mat = new THREE.MeshStandardMaterial({
          side: THREE.DoubleSide, roughness: 0.9, metalness: 0.0,
          polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
          color: url ? 0xffffff : new THREE.Color().setScalar(0.8 + (i % 5) * 0.04),
        })
        if (url) {
          const tex = loader.load(url)
          tex.wrapS = tex.wrapT = THREE.RepeatWrapping
          tex.magFilter = THREE.NearestFilter          // block textures stay crisp
          tex.colorSpace = THREE.SRGBColorSpace
          mat.map = tex
        }
        return mat
      })
      mats.push(new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, color: 0xcccccc }))  // faces with no material
      for (const g of groups) tgeom.addGroup(g.start, g.count, g.material < nMat ? g.material : nMat)
      this.parts.textured = new THREE.Mesh(tgeom, mats)
      this.faceOrder = order
      this.group.add(this.parts.textured)
      this.setTextured(this.texturedOn)
    }
```

  - Add the toggle and a helper that every look change goes through:

```ts
  setTextured(on: boolean) {
    this.texturedOn = on
    const hasTextured = !!this.parts.textured
    if (this.parts.textured) this.parts.textured.visible = on
    if (this.parts.facade) this.parts.facade.visible = !(on && hasTextured)
  }

  /** Every material the model's surface is drawn with, shaded and textured. */
  private surfaceMaterials(): THREE.MeshStandardMaterial[] {
    const out: THREE.MeshStandardMaterial[] = []
    for (const mesh of [this.parts.facade, this.parts.textured]) {
      if (!mesh) continue
      const m = mesh.material
      out.push(...((Array.isArray(m) ? m : [m]) as THREE.MeshStandardMaterial[]))
    }
    return out
  }
```

  - `setXRay`, `setOnesidedDiagnostic`, `setDoubleSided` and Task 9's `setErrorOverlay` (isolate) now
    loop over `this.surfaceMaterials()` instead of touching only `this.parts.facade.material`.
  - Picking (`setupPicking`) raycasts the visible surface and maps the slot back to the face number:

```ts
      const target = this.parts.textured?.visible ? this.parts.textured : this.parts.facade
      const hits = raycaster.intersectObject(target!)
      if (hits.length > 0 && hits[0].faceIndex !== undefined) {
        const slot = hits[0].faceIndex
        const faceId = target === this.parts.textured && this.faceOrder ? this.faceOrder[slot] : slot
        this.onPick(faceId, hits[0].point)
      }
```

  - In `clear()`: dispose each textured material's `map` too (`(m as any).map?.dispose()`), and reset
    `this.faceOrder = undefined`.

- [ ] **Step 6: The toggle.**
  - In `web/src/composables/useLayers.ts`, add `textures: boolean` to `LayerState`, `textures: true`
    to the defaults, and `u: 'textures'` to `HOTKEYS`. Update `useLayers.test.ts` where it lists the
    hotkeys or defaults, and run it.
  - In `WorkspaceView.vue`:
    - pass the version id: `viewA.loadModel(snap, snapshotVersion.value.id)` and
      `viewB.loadModel(fix, fixedVersion.value.id)`;
    - add a "Textures [U]" checkbox to the layer toolbar, copying the existing checkboxes' markup;
    - where the layers are applied to both views (about lines 482-496), add
      `viewA.setTextured(layers.textures)` and `viewB.setTextured(layers.textures)`.

- [ ] **Step 7: Type-check and run all web tests**

Run: `pnpm --dir web exec vue-tsc --noEmit` and `pnpm --dir web exec vitest run`
Expected: no new type errors; all tests pass.

- [ ] **Step 8: Commit**

```bash
git add web/src/utils/materialGroups.ts web/src/utils/materialGroups.test.ts web/src/three/Viewport.ts web/src/composables/useLayers.ts web/src/composables/useLayers.test.ts web/src/views/WorkspaceView.vue
git commit -m "feat(web): the 3D viewer shows the model's real textures, with a Textures toggle" -m "Textured, the export's coincident faces z-fight as they do in Unity, so the flicker is seen as it really is; the error filter's colours draw on top." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

Task 11's browser check adds:
- CHTM 5th floor shows its block textures;
- the diagonal wall at about (1893, 22949) visibly flickers as the camera moves;
- "Textures" off returns the grey shading.

