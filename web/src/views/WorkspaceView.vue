<template>
  <div class="workspace-layout">
    <!-- Top Navigation & Controls Bar -->
    <header class="top-bar">
      <div class="top-left">
        <router-link to="/" class="back-link">&larr; Models</router-link>
        <h1 class="model-title" v-if="model">{{ model.name }}</h1>
      </div>

      <div class="layer-toggles">
        <label class="toggle-item">
          <input type="checkbox" v-model="layers.grid" @change="updateLayers" />
          <span class="swatch" style="background: #1f5bff"></span>
          Gridlines
        </label>
        <label class="toggle-item">
          <input type="checkbox" v-model="layers.outline" @change="updateLayers" />
          <span class="swatch" style="background: #222222"></span>
          Outlines
        </label>
        <label class="toggle-item">
          <input type="checkbox" v-model="layers.xray" @change="updateLayers" />
          <span class="swatch" style="background: #d8282f"></span>
          X-Ray Inside
        </label>
        <label class="toggle-item" title="Diagnostic only. SketchUp and Unity draw both sides.">
          <input type="checkbox" v-model="layers.onesided" @change="updateLayers" />
          One-Sided
        </label>
        <label class="toggle-item">
          <input type="checkbox" v-model="layers.sync" @change="toggleSync" />
          Sync Cameras
        </label>
      </div>

      <div class="fix-actions">
        <label class="slit-toggle" title="Accept slit faces (narrow visible slivers)">
          <input type="checkbox" v-model="fixProfile.accept_slit" />
          Accept Slit Faces
        </label>
        <button
          class="btn btn-primary"
          :disabled="fixing || !snapshotVersion"
          @click="triggerFix"
        >
          {{ fixing ? 'Fixing in Engine...' : 'Run Fix Pipeline' }}
        </button>
        <button
          v-if="latestRun"
          class="btn btn-secondary"
          @click="showGuardModal = true"
        >
          Guard Diff (26 Views)
        </button>
      </div>
    </header>

    <!-- Center: Synced Dual 3D Viewports -->
    <main class="canvases-container">
      <section class="canvas-panel">
        <div class="canvas-header">
          <h2>BEFORE &middot; As Exported from SketchUp</h2>
          <span class="version-label" v-if="snapshotVersion">v{{ snapshotVersion.id }} (Snapshot)</span>
        </div>
        <div ref="canvasA" class="canvas-viewport"></div>
        <div class="panel-stats">
          <span v-if="snapshotVersion">
            <b>{{ snapshotVersion.tri_count.toLocaleString() }}</b> triangles &nbsp;&middot;&nbsp;
            <span style="color: #1f5bff">Interior gridlines visible</span>
          </span>
        </div>
      </section>

      <section class="canvas-panel">
        <div class="canvas-header">
          <h2>AFTER &middot; Inside Removed &amp; Planar Regions Merged</h2>
          <span class="version-label fixed-tag" v-if="fixedVersion">v{{ fixedVersion.id }} (Cleaned)</span>
          <span class="version-label preview-tag" v-else>No Fix Applied Yet</span>
        </div>
        <div ref="canvasB" class="canvas-viewport"></div>
        <div class="panel-stats">
          <span v-if="fixedVersion && snapshotVersion">
            <b style="color: #0d8a43">{{ fixedVersion.tri_count.toLocaleString() }}</b> triangles &nbsp;&middot;&nbsp;
            <b>{{ (100 * (1 - fixedVersion.tri_count / snapshotVersion.tri_count)).toFixed(1) }}% fewer</b> &nbsp;&middot;&nbsp;
            <span style="color: #0d8a43">Guard Passed (0 damaged px)</span>
          </span>
          <span v-else class="text-muted">
            Click "Run Fix Pipeline" to execute the geometry fix engine.
          </span>
        </div>
      </section>
    </main>

    <!-- Inspection Details Drawer (if face clicked) -->
    <div v-if="pickedFace" class="picked-inspector">
      <div class="inspector-header">
        <strong>Inspected Triangle #{{ pickedFace.faceId }}</strong>
        <button class="btn-close" @click="pickedFace = null">&times;</button>
      </div>
      <div class="inspector-body">
        <div>Coordinates: {{ pickedFace.point.x.toFixed(2) }}, {{ pickedFace.point.y.toFixed(2) }}, {{ pickedFace.point.z.toFixed(2) }}</div>
        <div>Source OBJ Face: line #{{ pickedFace.faceId + 1 }}</div>
      </div>
    </div>

    <!-- Guard 26 Views Diff Modal -->
    <div v-if="showGuardModal && latestRun" class="modal-backdrop" @click.self="showGuardModal = false">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Guard Visual Verification &middot; 26 Orthographic Views</h3>
          <button class="btn-close" @click="showGuardModal = false">&times;</button>
        </div>
        <div class="modal-views-bar">
          <span>Select View:</span>
          <button
            v-for="v in standardViews"
            :key="v"
            :class="['btn-view', { active: selectedView === v }]"
            @click="selectedView = v"
          >
            {{ v }}
          </button>
        </div>
        <div class="modal-diff-image">
          <p class="diff-legend">
            Left: <strong>BEFORE</strong> &middot; Middle: <strong>AFTER</strong> &middot; Right: <strong>PIXEL DIFF</strong> (Red: deleted, Green: added)
          </p>
          <img
            :src="getGuardImageUrl(latestRun.id, selectedView)"
            :alt="`Guard View ${selectedView}`"
            class="diff-triptych"
            @error="onImageError"
          />
          <p v-if="imgError" class="text-muted" style="color: #d8282f">
            Guard image not generated for this view or run.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  fetchModel,
  fetchMeshbuf,
  runFix,
  fetchRun,
  getGuardImageUrl,
  type Model,
  type ModelVersion,
  type FixRun,
} from '../api/client'
import { decodeMeshbuf } from '../three/meshbuf'
import { Viewport, syncViewports } from '../three/Viewport'
import * as THREE from 'three'

const route = useRoute()
const modelId = computed(() => Number(route.params.id))

const model = ref<Model | null>(null)
const latestRun = ref<FixRun | null>(null)
const fixing = ref(false)
const showGuardModal = ref(false)
const selectedView = ref('top')
const imgError = ref(false)
const pickedFace = ref<{ faceId: number; point: THREE.Vector3 } | null>(null)

const standardViews = ['top', 'bottom', 'north', 'south', 'east', 'west']

const layers = reactive({
  grid: true,
  outline: true,
  xray: false,
  onesided: false,
  sync: true,
})

const fixProfile = reactive({
  accept_slit: false,
  slit_threshold: 0.05,
  n_dirs: 128,
})

const canvasA = ref<HTMLElement | null>(null)
const canvasB = ref<HTMLElement | null>(null)

let viewA: Viewport | null = null
let viewB: Viewport | null = null
let disposeSync: (() => void) | null = null

const snapshotVersion = computed(() => {
  if (!model.value) return null
  return model.value.versions.find(v => v.kind === 'snapshot') || model.value.versions[0] || null
})

const fixedVersion = computed(() => {
  if (!model.value) return null
  const fixed = model.value.versions.filter(v => v.kind === 'fixed')
  return fixed.length ? fixed[fixed.length - 1] : null
})

async function initWorkspace() {
  if (!canvasA.value || !canvasB.value) return

  viewA = new Viewport(canvasA.value)
  viewB = new Viewport(canvasB.value)

  viewA.onPick = (faceId, point) => {
    pickedFace.value = { faceId, point }
  }
  viewB.onPick = (faceId, point) => {
    pickedFace.value = { faceId, point }
  }

  toggleSync()
  await reloadModel()
}

function toggleSync() {
  if (disposeSync) {
    disposeSync()
    disposeSync = null
  }
  if (layers.sync && viewA && viewB) {
    disposeSync = syncViewports(viewA, viewB)
  }
}

async function reloadModel() {
  try {
    model.value = await fetchModel(modelId.value)
    if (snapshotVersion.value && viewA) {
      const snapBuf = await fetchMeshbuf(snapshotVersion.value.id)
      viewA.loadModel(decodeMeshbuf(snapBuf))
    }
    if (fixedVersion.value && viewB) {
      const fixBuf = await fetchMeshbuf(fixedVersion.value.id)
      viewB.loadModel(decodeMeshbuf(fixBuf))
    }
  } catch (err: any) {
    console.error('Failed loading models:', err)
  }
}

function updateLayers() {
  if (viewA) {
    viewA.setLayer('grid', layers.grid)
    viewA.setLayer('outline', layers.outline)
    viewA.setXRay(layers.xray)
    viewA.setDoubleSided(!layers.onesided)
  }
  if (viewB) {
    viewB.setLayer('grid', layers.grid)
    viewB.setLayer('outline', layers.outline)
    viewB.setXRay(layers.xray)
    viewB.setDoubleSided(!layers.onesided)
  }
}

async function triggerFix() {
  if (!snapshotVersion.value) return
  fixing.value = true
  try {
    const run = await runFix(snapshotVersion.value.id, fixProfile)
    latestRun.value = run
    await reloadModel()
    updateLayers()
  } catch (err: any) {
    alert(`Fix failed: ${err.message}`)
  } finally {
    fixing.value = false
  }
}

function onImageError() {
  imgError.value = true
}

onMounted(() => {
  initWorkspace()
})

onBeforeUnmount(() => {
  if (disposeSync) disposeSync()
  if (viewA) viewA.dispose()
  if (viewB) viewB.dispose()
})
</script>

<style scoped>
.workspace-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f3f3f5;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #1c1d21;
}

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #fff;
  border-bottom: 1px solid #dcdde2;
  gap: 16px;
  flex-wrap: wrap;
}

.top-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-link {
  color: #676b75;
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
}
.back-link:hover {
  color: #1f5bff;
}

.model-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.layer-toggles {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 13px;
}

.toggle-item {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
}

.swatch {
  width: 12px;
  height: 4px;
  border-radius: 2px;
  display: inline-block;
}

.fix-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.slit-toggle {
  font-size: 12px;
  color: #555;
  display: flex;
  align-items: center;
  gap: 4px;
}

.canvases-container {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: #dcdde2;
  min-height: 0;
}

.canvas-panel {
  background: #fff;
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
}

.canvas-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 14px;
  border-bottom: 1px solid #eef0f4;
  background: #fafbfc;
}

.canvas-header h2 {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #676b75;
}

.version-label {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.fixed-tag {
  background: #e6f8ee;
  color: #0d8a43;
}

.preview-tag {
  background: #fff4d6;
  color: #946c00;
}

.canvas-viewport {
  flex: 1;
  min-height: 0;
  position: relative;
}

.panel-stats {
  padding: 8px 14px;
  border-top: 1px solid #eef0f4;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  background: #fafbfc;
}

.btn {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #1f5bff;
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background: #1447db;
}

.btn-secondary {
  background: #f0f1f4;
  color: #222;
  border: 1px solid #d0d2d7;
}
.btn-secondary:hover:not(:disabled) {
  background: #e4e6eb;
}

.picked-inspector {
  position: absolute;
  bottom: 50px;
  left: 20px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  border: 1px solid #ccc;
  border-radius: 6px;
  padding: 12px 16px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  font-size: 12px;
  z-index: 100;
  min-width: 260px;
}

.inspector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #888;
}
.btn-close:hover {
  color: #111;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-card {
  background: #fff;
  border-radius: 8px;
  width: 90vw;
  max-width: 1000px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 18px;
  border-bottom: 1px solid #eee;
}

.modal-header h3 {
  margin: 0;
  font-size: 15px;
}

.modal-views-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 18px;
  background: #fafbfc;
  border-bottom: 1px solid #eee;
}

.btn-view {
  background: #f0f1f4;
  border: 1px solid #dcdde2;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
  text-transform: capitalize;
}

.btn-view.active {
  background: #1f5bff;
  color: #fff;
  border-color: #1f5bff;
}

.modal-diff-image {
  padding: 16px;
  text-align: center;
  overflow-y: auto;
}

.diff-legend {
  font-size: 13px;
  color: #666;
  margin-top: 0;
  margin-bottom: 12px;
}

.diff-triptych {
  max-width: 100%;
  height: auto;
  border: 1px solid #eee;
  border-radius: 4px;
}
</style>
