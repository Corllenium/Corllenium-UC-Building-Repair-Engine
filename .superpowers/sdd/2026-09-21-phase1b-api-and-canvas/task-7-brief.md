### Task 7: Viewport, overlays, picking, camera sync

**Files:** Create `web\src\three\Viewport.ts`, `web\src\three\sync.ts`

**Interfaces — Consumes:** `DecodedMeshbuf`.
**Produces:**
`class Viewport { constructor(el: HTMLElement); load(d: DecodedMeshbuf): void; setEdgeClassVisible(cls: number, on: boolean): void; setOneSided(on: boolean): void; pick(clientX: number, clientY: number): number | null; highlight(triIndex: number | null): void; copyCameraFrom(o: Viewport): void; dispose(): void; readonly controls; readonly camera }`,
`EDGE_CLASSES = [{id:0,key:'real',label:'region outline',color:0x222222},{id:1,key:'removable',label:'gridline (removable)',color:0x1f5bff},{id:2,key:'open',label:'open edge',color:0xd8282f},{id:3,key:'nonmanifold',label:'3+ faces',color:0xff9500},{id:4,key:'tjunction',label:'T-junction',color:0xaf52de}]`,
`syncViewports(a: Viewport, b: Viewport, enabled: () => boolean): () => void`.

Port from `preview\index.html` (already verified in a browser): Z-up camera (`camera.up.set(0,0,1)` before creating
`OrbitControls`), hemisphere + directional light, `ResizeObserver`, canvas absolutely positioned inside an
`overflow:hidden` container, `fit()` with distance `size * 1.45`, busy-flag camera sync. Differences from the preview:

- Geometry comes from `positions` / `uvs` / `normals` attributes. One `BufferGeometry`, material **groups** built from
  runs of equal `triMaterial` (`geometry.addGroup(start*3, count*3, materialIndex)`), material array of
  `MeshLambertMaterial({ side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 })`.
  Index 65535 maps to one extra grey material appended at the end.
- Textures from `header.materials[i].texture` via `TextureLoader`: `RepeatWrapping` both axes,
  `magFilter = NearestFilter`, `colorSpace = SRGBColorSpace`. `null` -> plain `0xd0d0d4`.
- One `LineSegments` per edge class, built by filtering `edgePositions` with `edgeClass`.
- `setOneSided(true)` sets every mesh material to `THREE.FrontSide`; default and `false` is `DoubleSide`.
- `pick`: `Raycaster.setFromCamera` with NDC from the canvas rect, `intersectObject(mesh)`, return
  `triFaceId[hit.faceIndex]`. Geometry is non-indexed so `faceIndex` is the triangle index.
- `highlight(k)`: a 3-vertex mesh, `MeshBasicMaterial({ color: 0xffd400, depthTest: false, side: DoubleSide })`, `renderOrder = 10`.
- `dispose()`: cancel the animation frame, disconnect the observer, dispose geometries, materials, textures, renderer.

- [ ] **Step 1:** Write `Viewport.ts` and `sync.ts` as specified. No unit test: WebGL has no headless target here.
  Its proof is Task 8's browser verification. State that in the report, do not claim it is tested.
- [ ] **Step 2:** `pnpm --dir web build`. Expected: exits 0 with no type errors.
- [ ] **Step 3:** Commit `feat(web): three.js viewport with edge classes, picking, camera sync`.

---

