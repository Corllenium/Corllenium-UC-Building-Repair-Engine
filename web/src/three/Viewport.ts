import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { DecodedMeshbuf } from './meshbuf'

export const EDGE_REAL = 0
export const EDGE_REMOVABLE = 1
export const EDGE_OPEN = 2
export const EDGE_NONMANIFOLD = 3
export const EDGE_TJUNCTION = 4

const COLORS = {
  grid: 0x1f5bff,     // blue: removable gridlines
  outline: 0x222222,  // dark: real region borders
  tri: 0x9aa0a8,      // gray: triangle diagonals
  nonmanifold: 0xd8282f, // red: non-manifold edges
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
    grid?: THREE.LineSegments
    outline?: THREE.LineSegments
    tri?: THREE.LineSegments
    creases?: THREE.LineSegments
    hidden?: THREE.Mesh
    backfaceDiagnostic?: THREE.Mesh
  } = {}
  private lastPositions?: Float32Array
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
        if (Array.isArray(m)) m.forEach(x => x.dispose())
        else m.dispose()
      }
      this.group.remove(o)
    }
    this.parts = {}
  }

  loadModel(data: DecodedMeshbuf) {
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

    // Wireframe triangle edges
    const triLines: number[] = []
    for (let f = 0; f < nFaces; f++) {
      const idx = f * 9
      const ax = positions[idx], ay = positions[idx + 1], az = positions[idx + 2]
      const bx = positions[idx + 3], by = positions[idx + 4], bz = positions[idx + 5]
      const cx = positions[idx + 6], cy = positions[idx + 7], cz = positions[idx + 8]
      // a -> b
      triLines.push(ax, ay, az, bx, by, bz)
      // b -> c
      triLines.push(bx, by, bz, cx, cy, cz)
      // c -> a
      triLines.push(cx, cy, cz, ax, ay, az)
    }
    if (triLines.length > 0) {
      const tGeom = new THREE.BufferGeometry()
      tGeom.setAttribute('position', new THREE.Float32BufferAttribute(triLines, 3))
      const tLines = new THREE.LineSegments(
        tGeom,
        new THREE.LineBasicMaterial({ color: COLORS.tri, linewidth: 1, transparent: true, opacity: 0.6 })
      )
      tLines.visible = false
      this.parts.tri = tLines
      this.group.add(tLines)
    }

    // Soft creases: edges between adjacent faces within a normal angle threshold (2° to 45°)
    const edgeMap = new Map<string, { nx: number; ny: number; nz: number; p1: [number, number, number]; p2: [number, number, number] }>()
    const creaseLines: number[] = []

    function vKey(x: number, y: number, z: number): string {
      return `${Math.round(x * 1000)},${Math.round(y * 1000)},${Math.round(z * 1000)}`
    }

    for (let f = 0; f < nFaces; f++) {
      const idx = f * 9
      const ax = positions[idx], ay = positions[idx + 1], az = positions[idx + 2]
      const bx = positions[idx + 3], by = positions[idx + 4], bz = positions[idx + 5]
      const cx = positions[idx + 6], cy = positions[idx + 7], cz = positions[idx + 8]
      const kA = vKey(ax, ay, az)
      const kB = vKey(bx, by, bz)
      const kC = vKey(cx, cy, cz)

      const nx = data.normals[idx]
      const ny = data.normals[idx + 1]
      const nz = data.normals[idx + 2]

      const edges: [string, string, [number, number, number], [number, number, number]][] = [
        [kA, kB, [ax, ay, az], [bx, by, bz]],
        [kB, kC, [bx, by, bz], [cx, cy, cz]],
        [kC, kA, [cx, cy, cz], [ax, ay, az]],
      ]

      for (const [k1, k2, p1, p2] of edges) {
        const edgeKey = k1 < k2 ? `${k1}|${k2}` : `${k2}|${k1}`
        const existing = edgeMap.get(edgeKey)
        if (existing) {
          const dot = existing.nx * nx + existing.ny * ny + existing.nz * nz
          // angle between 2 deg (dot ~ 0.9994) and 45 deg (dot ~ 0.707)
          if (dot > 0.707 && dot < 0.999) {
            creaseLines.push(p1[0], p1[1], p1[2], p2[0], p2[1], p2[2])
          }
          edgeMap.delete(edgeKey)
        } else {
          edgeMap.set(edgeKey, { nx, ny, nz, p1, p2 })
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
      cLines.visible = false
      this.parts.creases = cLines
      this.group.add(cLines)
    }

    // Separate edges into gridlines (removable) and outlines (real)
    const edgePos = data.edgePositions
    const edgeCls = data.edgeClass
    const nEdges = edgeCls.length

    const gridLines: number[] = []
    const outlineLines: number[] = []

    for (let e = 0; e < nEdges; e++) {
      const cls = edgeCls[e]
      const idx = e * 6
      const arr = (cls === EDGE_REMOVABLE || cls === EDGE_TJUNCTION) ? gridLines : outlineLines
      for (let k = 0; k < 6; k++) {
        arr.push(edgePos[idx + k])
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

  setLayer(layer: 'grid' | 'outline' | 'tri' | 'creases' | 'hidden', visible: boolean) {
    if (this.parts[layer]) {
      this.parts[layer]!.visible = visible
    }
  }

  setOnesidedDiagnostic(enabled: boolean) {
    if (this.parts.facade) {
      const mat = this.parts.facade.material as THREE.MeshStandardMaterial
      mat.side = enabled ? THREE.FrontSide : THREE.DoubleSide
      mat.needsUpdate = true
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
    if (this.parts.facade) {
      this.parts.facade.material.side = doubleSided ? THREE.DoubleSide : THREE.FrontSide
      this.parts.facade.material.needsUpdate = true
    }
  }

  setXRay(xray: boolean) {
    if (this.parts.facade) {
      const m = this.parts.facade.material as THREE.MeshStandardMaterial
      m.transparent = xray
      m.opacity = xray ? 0.25 : 1.0
      m.depthWrite = !xray
      m.needsUpdate = true
    }
  }

  private setupPicking() {
    const raycaster = new THREE.Raycaster()
    const mouse = new THREE.Vector2()

    this.el.addEventListener('click', (e: MouseEvent) => {
      if (!this.onPick || !this.parts.facade) return
      const rect = this.el.getBoundingClientRect()
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1

      raycaster.setFromCamera(mouse, this.camera)
      const hits = raycaster.intersectObject(this.parts.facade)
      if (hits.length > 0 && hits[0].faceIndex !== undefined) {
        this.onPick(hits[0].faceIndex, hits[0].point)
      }
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
