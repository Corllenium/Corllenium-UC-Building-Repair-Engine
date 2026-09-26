import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { DecodedMeshbuf } from './meshbuf'
import { groupByMaterial, textureUrl } from '../utils/materialGroups'
import { chooseFace, type SlotHit } from '../utils/errorLayers'

export const EDGE_REAL = 0
export const EDGE_REMOVABLE = 1
export const EDGE_OPEN = 2
export const EDGE_NONMANIFOLD = 3
export const EDGE_TJUNCTION = 4
export const EDGE_SOFT = 5

const COLORS = {
  grid: 0x1f5bff,     // blue: removable gridlines
  outline: 0x222222,  // dark: real region borders
  tri: 0x9aa0a8,      // gray: triangle diagonals
  nonmanifold: 0xd8282f, // red: non-manifold edges
}

// Crack dots and open edges sit exactly on a real surface (a T-junction point, an edge), so a
// plain depth test would z-fight that surface and lose. After three's own projection, the vertex
// shader re-projects each vertex from its view-space position scaled by 0.998 toward the eye: the
// same pixel (the camera is a PerspectiveCamera, which maps every point on a line through the eye
// to one pixel) at the depth of a point 0.2 % of its distance nearer. That beats the surface it
// sits on at every zoom, and any real wall in front hides it unless the wall is within that 0.2 %:
// 6.5 in at CHTM's overview (a 24-bit depth step there is 0.56 in), 0.19 in at the 96 in fly-to.
// The constant NDC nudge this replaces showed them through about 114 ft of walls at the overview
// (review I2). Used by both setErrorLines and setErrorPoints.
export const DEPTH_BIAS_GLSL = '#include <project_vertex>\n  gl_Position = projectionMatrix * vec4(mvPosition.xyz * 0.998, 1.0);'

/** The error overlay's material: its vertex colours, drawn a hair in front of the surface each
 *  face lies on. Both sides are drawn, which also lets a pick ray meet a face from behind: the
 *  raycaster skips a FrontSide triangle's back, and an interior flicker face faces away from half
 *  the views (review I3). */
export function errorOverlayMaterial(): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({
    vertexColors: true, side: THREE.DoubleSide,
    polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
  })
}

export class Viewport {
  el: HTMLElement
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  renderer: THREE.WebGLRenderer
  controls: OrbitControls
  group: THREE.Group
  parts: {
    facade?: THREE.Mesh
    textured?: THREE.Mesh
    grid?: THREE.LineSegments
    outline?: THREE.LineSegments
    tri?: THREE.LineSegments
    creases?: THREE.LineSegments
    hidden?: THREE.Mesh
    backfaceDiagnostic?: THREE.Mesh
    errors?: THREE.Mesh
    errorLines?: THREE.LineSegments
    errorPoints?: THREE.Points
  } = {}
  private currentData?: DecodedMeshbuf
  private lastPositions?: Float32Array
  private faceOrder?: Uint32Array
  private overlayFaceIds: number[] | null = null   // the face drawn in each error-overlay slot
  private xray = false
  private isolate = false
  private texturedOn = true
  private blinkA: Float32Array | null = null
  private blinkB: Float32Array | null = null
  private blinkPhase = -1
  private animId: number = 0
  private resizeObserver: ResizeObserver
  onPick?: (faceId: number, point: THREE.Vector3) => void

  constructor(el: HTMLElement) {
    this.el = el
    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0xf6f6f8)

    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 1e6)
    this.camera.up.set(0, 0, 1) // SketchUp exports are Z-up

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    el.appendChild(this.renderer.domElement)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.05

    // Lighting
    const hemi = new THREE.HemisphereLight(0xffffff, 0x9a9aa2, 1.2)
    hemi.position.set(0, 0, 1)
    const sun = new THREE.DirectionalLight(0xffffff, 1.2)
    sun.position.set(0.4, -0.5, 0.9).normalize()
    this.scene.add(hemi, sun)

    this.group = new THREE.Group()
    this.scene.add(this.group)

    this.resizeObserver = new ResizeObserver(() => this.resize())
    this.resizeObserver.observe(el)
    this.resize()

    this.setupPicking()
    this.loop()
  }

  private loop = () => {
    this.controls.update()
    if (this.blinkA && this.blinkB && this.parts.errors) {
      const phase = Math.floor(performance.now() / 125) % 2   // 4 swaps a second
      if (phase !== this.blinkPhase) {
        const attr = this.parts.errors.geometry.getAttribute('color') as THREE.BufferAttribute
        const blink = phase === 0 ? this.blinkA : this.blinkB
        if (blink.length === attr.array.length) {
          attr.copyArray(blink)
          attr.needsUpdate = true
        }
        this.blinkPhase = phase
      }
    }
    this.renderer.render(this.scene, this.camera)
    this.animId = requestAnimationFrame(this.loop)
  }

  resize() {
    const w = Math.max(1, this.el.clientWidth)
    const h = Math.max(1, this.el.clientHeight)
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  clear() {
    for (const o of [...this.group.children]) {
      if ((o as any).geometry) (o as any).geometry.dispose()
      if ((o as any).material) {
        const m = (o as any).material
        const mats = Array.isArray(m) ? m : [m]
        mats.forEach(x => { x.map?.dispose(); x.dispose() })
      }
      this.group.remove(o)
    }
    this.parts = {}
    this.faceOrder = undefined
    this.overlayFaceIds = null
    this.blinkA = this.blinkB = null
  }

  loadModel(data: DecodedMeshbuf, versionId?: number) {
    this.clear()

    const nFaces = data.header.counts.faces
    const positions = data.positions
    const colors = new Float32Array(nFaces * 9)

    // Assign subtle shades per material or default light gray
    for (let f = 0; f < nFaces; f++) {
      const mi = data.triMaterial[f]
      const shade = 0.8 + ((mi % 5) * 0.04)
      for (let k = 0; k < 9; k++) {
        colors[f * 9 + k] = shade
      }
    }

    // Geometry
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geom.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3))
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3))

    const mat = new THREE.MeshStandardMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      roughness: 0.8,
      metalness: 0.1,
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    })

    const mesh = new THREE.Mesh(geom, mat)
    this.parts.facade = mesh
    this.group.add(mesh)
    this.lastPositions = positions

    // Backface diagnostic mesh (magenta / red for backfaces when one-sided diagnostic is active)
    const backfaceMat = new THREE.MeshBasicMaterial({
      color: 0xff007f, // magenta
      side: THREE.BackSide,
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    })
    const backfaceMesh = new THREE.Mesh(geom, backfaceMat)
    backfaceMesh.visible = false
    this.parts.backfaceDiagnostic = backfaceMesh
    this.group.add(backfaceMesh)
    this.currentData = data

    // Separate edges into gridlines (removable) and outlines (real borders)
    // EDGE_SOFT edges are reserved for creases and excluded from dark outlines
    const edgePos = data.edgePositions
    const edgeCls = data.edgeClass
    const nEdges = edgeCls.length

    const gridLines: number[] = []
    const outlineLines: number[] = []

    for (let e = 0; e < nEdges; e++) {
      const cls = edgeCls[e]
      const idx = e * 6
      if (cls === EDGE_REMOVABLE || cls === EDGE_TJUNCTION) {
        for (let k = 0; k < 6; k++) {
          gridLines.push(edgePos[idx + k])
        }
      } else if (cls !== EDGE_SOFT) {
        for (let k = 0; k < 6; k++) {
          outlineLines.push(edgePos[idx + k])
        }
      }
    }

    if (gridLines.length > 0) {
      const gGeom = new THREE.BufferGeometry()
      gGeom.setAttribute('position', new THREE.Float32BufferAttribute(gridLines, 3))
      const gLines = new THREE.LineSegments(
        gGeom,
        new THREE.LineBasicMaterial({ color: COLORS.grid, linewidth: 1 })
      )
      this.parts.grid = gLines
      this.group.add(gLines)
    }

    if (outlineLines.length > 0) {
      const oGeom = new THREE.BufferGeometry()
      oGeom.setAttribute('position', new THREE.Float32BufferAttribute(outlineLines, 3))
      const oLines = new THREE.LineSegments(
        oGeom,
        new THREE.LineBasicMaterial({ color: COLORS.outline, linewidth: 1.5 })
      )
      this.parts.outline = oLines
      this.group.add(oLines)
    }

    // A textured facade, drawn instead of the flat-shaded one when textures are on and the
    // model has any. Non-indexed geometry sorted by material so each material can be one
    // three.js draw group; faceOrder maps a slot in that sort back to the real face id.
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

    // Fit camera to bounding box
    const box = new THREE.Box3().setFromBufferAttribute(geom.getAttribute('position') as THREE.BufferAttribute)
    const c = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3()).length()

    this.controls.target.copy(c)
    this.camera.position.copy(c).add(new THREE.Vector3(-0.45, -0.55, 0.7).normalize().multiplyScalar(size * 1.45))
    this.camera.near = Math.max(0.01, size / 2000)
    this.camera.far = size * 20
    this.camera.updateProjectionMatrix()
    this.controls.update()
  }

  private buildTriangles() {
    if (!this.currentData || this.parts.tri) return
    const positions = this.currentData.positions
    const nFaces = this.currentData.header.counts.faces
    const triLines: number[] = []
    for (let f = 0; f < nFaces; f++) {
      const idx = f * 9
      const ax = positions[idx], ay = positions[idx + 1], az = positions[idx + 2]
      const bx = positions[idx + 3], by = positions[idx + 4], bz = positions[idx + 5]
      const cx = positions[idx + 6], cy = positions[idx + 7], cz = positions[idx + 8]
      triLines.push(ax, ay, az, bx, by, bz)
      triLines.push(bx, by, bz, cx, cy, cz)
      triLines.push(cx, cy, cz, ax, ay, az)
    }
    if (triLines.length > 0) {
      const tGeom = new THREE.BufferGeometry()
      tGeom.setAttribute('position', new THREE.Float32BufferAttribute(triLines, 3))
      const tLines = new THREE.LineSegments(
        tGeom,
        new THREE.LineBasicMaterial({ color: COLORS.tri, linewidth: 1, transparent: true, opacity: 0.6 })
      )
      this.parts.tri = tLines
      this.group.add(tLines)
    }
  }

  private buildCreases() {
    if (!this.currentData || this.parts.creases) return
    const edgePos = this.currentData.edgePositions
    const edgeCls = this.currentData.edgeClass
    const nEdges = edgeCls.length
    const creaseLines: number[] = []
    for (let e = 0; e < nEdges; e++) {
      if (edgeCls[e] === EDGE_SOFT) {
        const idx = e * 6
        for (let k = 0; k < 6; k++) {
          creaseLines.push(edgePos[idx + k])
        }
      }
    }
    if (creaseLines.length > 0) {
      const cGeom = new THREE.BufferGeometry()
      cGeom.setAttribute('position', new THREE.Float32BufferAttribute(creaseLines, 3))
      const cLines = new THREE.LineSegments(
        cGeom,
        new THREE.LineBasicMaterial({ color: 0x00b4d8, linewidth: 1.5 })
      )
      this.parts.creases = cLines
      this.group.add(cLines)
    }
  }

  setLayer(layer: 'grid' | 'outline' | 'tri' | 'creases' | 'hidden', visible: boolean) {
    if (visible) {
      if (layer === 'tri' && !this.parts.tri) {
        this.buildTriangles()
      } else if (layer === 'creases' && !this.parts.creases) {
        this.buildCreases()
      }
    }
    if (this.parts[layer]) {
      this.parts[layer]!.visible = visible
    }
  }

  setRemovedFaces(faceIndices: number[] | Set<number>) {
    this.setHiddenFaces(faceIndices)
  }

  setOnesidedDiagnostic(enabled: boolean) {
    for (const m of this.surfaceMaterials()) {
      m.side = enabled ? THREE.FrontSide : THREE.DoubleSide
      m.needsUpdate = true
    }
    if (this.parts.backfaceDiagnostic) {
      this.parts.backfaceDiagnostic.visible = enabled
    }
  }

  setHiddenFaces(faceIndices: number[] | Set<number>) {
    if (this.parts.hidden) {
      this.group.remove(this.parts.hidden)
      this.parts.hidden.geometry.dispose()
      ;(this.parts.hidden.material as THREE.Material).dispose()
      delete this.parts.hidden
    }
    if (!this.lastPositions) return

    const indices = Array.isArray(faceIndices) ? faceIndices : Array.from(faceIndices)
    if (indices.length === 0) return

    const hiddenVerts: number[] = []
    for (const f of indices) {
      const idx = f * 9
      if (idx + 8 < this.lastPositions.length) {
        for (let k = 0; k < 9; k++) {
          hiddenVerts.push(this.lastPositions[idx + k])
        }
      }
    }
    if (hiddenVerts.length === 0) return

    const hGeom = new THREE.BufferGeometry()
    hGeom.setAttribute('position', new THREE.Float32BufferAttribute(hiddenVerts, 3))
    hGeom.computeVertexNormals()
    const hMat = new THREE.MeshStandardMaterial({
      color: 0xff3344,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.75,
      depthWrite: false,
    })
    const hMesh = new THREE.Mesh(hGeom, hMat)
    hMesh.visible = false
    this.parts.hidden = hMesh
    this.group.add(hMesh)
  }

  setDoubleSided(doubleSided: boolean) {
    for (const m of this.surfaceMaterials()) {
      m.side = doubleSided ? THREE.DoubleSide : THREE.FrontSide
      m.needsUpdate = true
    }
  }

  setTextured(on: boolean) {
    this.texturedOn = on
    const hasTextured = !!this.parts.textured
    if (this.parts.textured) this.parts.textured.visible = on
    if (this.parts.facade) this.parts.facade.visible = !(on && hasTextured)
  }

  setXRay(xray: boolean) {
    this.xray = xray
    this.applyFacadeLook()
  }

  /** Every material the model's surface is drawn with, shaded and textured -- the flat facade
   *  and, when textures are on, the textured mesh's per-material list. */
  private surfaceMaterials(): THREE.MeshStandardMaterial[] {
    const out: THREE.MeshStandardMaterial[] = []
    for (const mesh of [this.parts.facade, this.parts.textured]) {
      if (!mesh) continue
      const m = mesh.material
      out.push(...((Array.isArray(m) ? m : [m]) as THREE.MeshStandardMaterial[]))
    }
    return out
  }

  /** Isolate wins over X-ray; either wins over the plain opaque look. Shared so toggling one
   *  never clobbers the other's material state, on the facade or the textured mesh alike. */
  private applyFacadeLook() {
    const materials = this.surfaceMaterials()
    for (const m of materials) {
      if (this.isolate) {
        m.transparent = true
        m.opacity = 0.08
        m.depthWrite = false
      } else if (this.xray) {
        m.transparent = true
        m.opacity = 0.25
        m.depthWrite = false
      } else {
        m.transparent = false
        m.opacity = 1.0
        m.depthWrite = true
      }
      m.needsUpdate = true
    }
  }

  private removePart(name: 'errors' | 'errorLines' | 'errorPoints') {
    const part = this.parts[name]
    if (!part) return
    this.group.remove(part)
    part.geometry.dispose()
    ;(part.material as THREE.Material).dispose()
    delete this.parts[name]
  }

  setErrorOverlay(faces: number[], colors: Float32Array, isolate: boolean) {
    this.removePart('errors')
    this.overlayFaceIds = null
    this.blinkA = this.blinkB = null   // stale buffers would be sized for the old overlay
    this.isolate = faces.length > 0 && isolate   // clearing the overlay always restores the normal look
    this.applyFacadeLook()
    if (!this.lastPositions || faces.length === 0) return
    const pos = new Float32Array(faces.length * 9)
    faces.forEach((f, slot) => pos.set(this.lastPositions!.subarray(f * 9, f * 9 + 9), slot * 9))
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geom.setAttribute('color', new THREE.BufferAttribute(colors.slice(), 3))
    this.parts.errors = new THREE.Mesh(geom, errorOverlayMaterial())
    this.overlayFaceIds = faces
    this.group.add(this.parts.errors)
    this.blinkPhase = -1
  }

  setErrorBlink(colorsA: Float32Array | null, colorsB: Float32Array | null) {
    this.blinkA = colorsA
    this.blinkB = colorsB
    this.blinkPhase = -1
  }

  setErrorLines(segments: Float32Array, color: number) {
    this.removePart('errorLines')
    if (segments.length === 0) return
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(segments.slice(), 3))
    const mat = new THREE.LineBasicMaterial({ color, depthTest: true, depthWrite: false })
    mat.onBeforeCompile = (shader) => {
      shader.vertexShader = shader.vertexShader.replace('#include <project_vertex>', DEPTH_BIAS_GLSL)
    }
    this.parts.errorLines = new THREE.LineSegments(geom, mat)
    this.parts.errorLines.renderOrder = 3
    this.group.add(this.parts.errorLines)
  }

  setErrorPoints(points: Float32Array, color: number) {
    this.removePart('errorPoints')
    if (points.length === 0) return
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(points.slice(), 3))
    const mat = new THREE.PointsMaterial({ color, size: 6, sizeAttenuation: false, depthTest: true, depthWrite: false })
    mat.onBeforeCompile = (shader) => {
      shader.vertexShader = shader.vertexShader.replace('#include <project_vertex>', DEPTH_BIAS_GLSL)
    }
    this.parts.errorPoints = new THREE.Points(geom, mat)
    this.parts.errorPoints.renderOrder = 3
    this.group.add(this.parts.errorPoints)
  }

  flyTo(centre: [number, number, number], size: number) {
    const target = new THREE.Vector3(...centre)
    const dir = this.camera.position.clone().sub(this.controls.target).normalize()
    if (dir.lengthSq() === 0) dir.set(0, -1, 0.3).normalize()
    this.controls.target.copy(target)
    this.camera.position.copy(target).add(dir.multiplyScalar(Math.max(size, 60) * 1.6))
    this.controls.update()
    this.controls.dispatchEvent({ type: 'change' } as any)   // lets syncViewports move the other panel
  }

  originOffset(): [number, number, number] {
    return (this.currentData?.header.origin_offset ?? [0, 0, 0]) as [number, number, number]
  }

  private setupPicking() {
    const raycaster = new THREE.Raycaster()
    const mouse = new THREE.Vector2()
    const firstHit = (mesh: THREE.Mesh | undefined): SlotHit<THREE.Vector3> | null => {
      const hit = mesh ? raycaster.intersectObject(mesh)[0] : undefined
      return hit && hit.faceIndex != null ? { faceIndex: hit.faceIndex, point: hit.point } : null
    }

    this.el.addEventListener('click', (e: MouseEvent) => {
      const target = this.parts.textured?.visible ? this.parts.textured : this.parts.facade
      if (!this.onPick || !target) return
      const rect = this.el.getBoundingClientRect()
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1

      raycaster.setFromCamera(mouse, this.camera)
      // In Isolate or X-ray the surface is a faded ghost, so the error overlay is tried first: a
      // click on a highlighted face picks it, not the wall in front of it (review I3).
      const ghosted = this.isolate || this.xray
      const pick = chooseFace(ghosted, ghosted ? firstHit(this.parts.errors) : null, this.overlayFaceIds,
        firstHit(target), target === this.parts.textured ? this.faceOrder ?? null : null)
      if (pick) this.onPick(pick.faceId, pick.point)
    })
  }

  dispose() {
    cancelAnimationFrame(this.animId)
    this.resizeObserver.disconnect()
    this.clear()
    this.renderer.dispose()
    if (this.renderer.domElement.parentElement) {
      this.renderer.domElement.parentElement.removeChild(this.renderer.domElement)
    }
  }
}

export function syncViewports(a: Viewport, b: Viewport): () => void {
  let isSyncing = false

  const sync = (src: Viewport, dst: Viewport) => () => {
    if (isSyncing) return
    isSyncing = true
    dst.camera.position.copy(src.camera.position)
    dst.camera.quaternion.copy(src.camera.quaternion)
    if (dst.camera.zoom !== src.camera.zoom || dst.camera.fov !== src.camera.fov) {
      dst.camera.zoom = src.camera.zoom
      dst.camera.fov = src.camera.fov
      dst.camera.updateProjectionMatrix()
    }
    dst.controls.target.copy(src.controls.target)
    dst.controls.update()
    isSyncing = false
  }

  const handleA = sync(a, b)
  const handleB = sync(b, a)

  a.controls.addEventListener('change', handleA)
  b.controls.addEventListener('change', handleB)

  return () => {
    a.controls.removeEventListener('change', handleA)
    b.controls.removeEventListener('change', handleB)
  }
}
