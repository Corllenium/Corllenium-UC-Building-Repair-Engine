<template>
  <div class="workspace-layout">
    <!-- Top Navigation & Controls Bar -->
    <header class="top-bar">
      <div class="top-left">
        <router-link to="/" class="back-link">&larr; Models</router-link>
        <h1 class="model-title" v-if="model">{{ model.name }}</h1>
      </div>

      <div class="layer-toggles">
        <label class="toggle-item" title="Hotkey: G">
          <input type="checkbox" v-model="layers.grid" @change="updateLayers" />
          <span class="swatch" style="background: #1f5bff"></span>
          Gridlines <kbd class="kbd-hint">G</kbd>
        </label>
        <label class="toggle-item" title="Hotkey: O">
          <input type="checkbox" v-model="layers.outline" @change="updateLayers" />
          <span class="swatch" style="background: #222222"></span>
          Outlines <kbd class="kbd-hint">O</kbd>
        </label>
        <label class="toggle-item" title="Hotkey: T">
          <input type="checkbox" v-model="layers.tri" @change="updateLayers" />
          <span class="swatch" style="background: #9aa0a8"></span>
          Triangles <kbd class="kbd-hint">T</kbd>
        </label>
        <label class="toggle-item" title="Hotkey: C">
          <input type="checkbox" v-model="layers.creases" @change="updateLayers" />
          <span class="swatch" style="background: #00b4d8"></span>
          Creases <kbd class="kbd-hint">C</kbd>
        </label>
        <label class="toggle-item" title="Hotkey: H">
          <input type="checkbox" v-model="layers.hidden" @change="updateLayers" />
          <span class="swatch" style="background: #ff3344"></span>
          Hidden Faces <kbd class="kbd-hint">H</kbd>
        </label>
        <label class="toggle-item" title="Diagnostic only: Inverted normal / backface detection. Hotkey: M">
          <input type="checkbox" v-model="layers.onesided" @change="updateLayers" />
          <span class="swatch" style="background: #ff007f"></span>
          One-Sided / Flipped <kbd class="kbd-hint">M</kbd>
        </label>
        <label class="toggle-item" title="Hotkey: X">
          <input type="checkbox" v-model="layers.xray" @change="updateLayers" />
          <span class="swatch" style="background: #d8282f"></span>
          X-Ray <kbd class="kbd-hint">X</kbd>
        </label>
        <label class="toggle-item" title="Hotkey: S">
          <input type="checkbox" v-model="layers.sync" @change="toggleSync" />
          Sync <kbd class="kbd-hint">S</kbd>
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
          v-if="latestRun && availableGuardViews.length > 0"
          class="btn btn-secondary"
          @click="showGuardModal = true"
        >
          Guard Diff ({{ availableGuardViews.length }} Views)
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
          <h2>AFTER &middot; {{ resultDesc ? resultDesc.heading : 'Inside Removed & Planar Regions Merged' }}</h2>
          <span class="version-label fixed-tag" v-if="fixedVersion">v{{ fixedVersion.id }} (Cleaned)</span>
          <span class="version-label preview-tag" v-else>No Fix Applied Yet</span>
        </div>
        <div ref="canvasB" class="canvas-viewport"></div>
        <div class="panel-stats">
          <div v-if="resultDesc && resultDesc.error" class="text-error" style="color: #d8282f">
            <strong>Fix failed:</strong> {{ resultDesc.error }}
          </div>
          <span v-else-if="fixedVersion && snapshotVersion">
            <b :style="{ color: resultDesc && !resultDesc.guardPassed ? '#d8282f' : '#0d8a43' }">{{ fixedVersion.tri_count.toLocaleString() }}</b> triangles &nbsp;&middot;&nbsp;
            <b>{{ (100 * (1 - fixedVersion.tri_count / snapshotVersion.tri_count)).toFixed(1) }}% fewer</b>
            <template v-if="resultDesc">
              &nbsp;&middot;&nbsp;
              <span :style="{ color: resultDesc.guardPassed ? '#0d8a43' : '#d8282f' }">{{ resultDesc.guardLine }}</span>
              <template v-if="resultDesc.backfacePx !== undefined">
                &nbsp;&middot;&nbsp; <span>{{ resultDesc.backfacePx.toLocaleString() }} backface px</span>
              </template>
              <template v-if="resultDesc.borderShiftPx !== undefined">
                &nbsp;&middot;&nbsp; <span>{{ resultDesc.borderShiftPx }} border shift</span>
              </template>
              <template v-if="resultDesc.skpSummary">
                &nbsp;&middot;&nbsp; <span class="skp-summary">{{ resultDesc.skpSummary }}</span>
              </template>
            </template>
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
        <strong>Inspected Triangle #{{ pickedFace.faceId }} ({{ pickedFace.viewKind.toUpperCase() }})</strong>
        <button class="btn-close" @click="pickedFace = null">&times;</button>
      </div>
      <div class="inspector-body">
        <div>Coordinates: {{ pickedFace.point.x.toFixed(2) }}, {{ pickedFace.point.y.toFixed(2) }}, {{ pickedFace.point.z.toFixed(2) }}</div>
        <div v-if="pickedFace.loading">Loading face details...</div>
        <div v-else-if="pickedFace.details">
          <div>{{ formatFaceSourceInfo(pickedFace.viewKind, pickedFace.details) }}</div>
          <div v-if="pickedFace.details.material">Material: {{ pickedFace.details.material }}</div>
        </div>
        <div v-else-if="pickedFace.error" class="text-error">{{ pickedFace.error }}</div>
      </div>
    </div>

    <!-- Guard 26 Views Diff Modal -->
    <div
      v-if="showGuardModal && latestRun"
      class="modal-backdrop"
      @click.self="showGuardModal = false"
    >
      <div class="modal-card">
        <div class="modal-header">
          <div class="modal-title-wrap">
            <h3>Guard Visual Verification &middot; Orthographic Diff</h3>
            <span class="view-indicator">View {{ currentViewIndex + 1 }} / {{ availableGuardViews.length }} &mdash; <kbd class="kbd-hint">&larr;</kbd> <kbd class="kbd-hint">&rarr;</kbd> to navigate</span>
          </div>
          <button class="btn-close" @click="showGuardModal = false">&times;</button>
        </div>
        <div class="modal-views-bar">
          <button class="btn-arrow" @click="prevGuardView">&larr; Prev</button>
          <div class="views-chips">
            <button
              v-for="v in availableGuardViews"
              :key="v"
              :class="['btn-view', { active: currentGuardView === v }]"
              @click="selectGuardView(v)"
            >
              {{ formatViewName(v) }}
            </button>
          </div>
          <button class="btn-arrow" @click="nextGuardView">Next &rarr;</button>
        </div>
        <div class="modal-diff-image">
          <p class="diff-legend">
            Left: <strong>BEFORE</strong> &middot; Middle: <strong>AFTER</strong> &middot; Right: <strong>PIXEL DIFF</strong> (Red: deleted, Green: added, Amber: moved)
          </p>
          <div class="image-wrapper">
            <img
              v-show="!imgError"
              :src="guardImageUrl"
              :alt="`Guard View ${currentGuardView}`"
              class="diff-triptych"
              @load="imgError = false"
              @error="imgError = true"
            />
            <div v-if="imgError" class="empty-guard-state">
              <p>Guard image not generated for view <strong>{{ currentGuardView }}</strong> in this run.</p>
              <p class="text-hint">Axis views (+x, -x, +y, -y, +z, -z) and failing oblique views generate guard renders.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  fetchModel,
  fetchMeshbuf,
  runFix,
  fetchRun,
  fetchFace,
  type Model,
  type ModelVersion,
  type FixRun,
  type FaceDetails,
} from '../api/client'
import { decodeMeshbuf } from '../three/meshbuf'
import { Viewport, syncViewports } from '../three/Viewport'
import { describeResult } from '../utils/describeResult'
import { formatFaceSourceInfo } from '../utils/faceInspection'
import { useLayers } from '../composables/useLayers'
import { useGuardViews, getGuardImageUrl, DEFAULT_GUARD_VIEWS } from '../composables/useGuardViews'
import * as THREE from 'three'

interface PickedFaceState {
  viewKind: 'before' | 'after'
  faceId: number
  point: THREE.Vector3
  details?: FaceDetails | null
  loading?: boolean
  error?: string | null
}

const route = useRoute()
const modelId = computed(() => Number(route.params.id))

const model = ref<Model | null>(null)
const latestRun = ref<FixRun | null>(null)
const fixing = ref(false)
const showGuardModal = ref(false)
const imgError = ref(false)
const pickedFace = ref<PickedFaceState | null>(null)

const resultDesc = computed(() => {
  if (!latestRun.value) return null
  return describeResult(latestRun.value.report_json || latestRun.value)
})

const {
  availableViews: availableGuardViews,
  currentView: currentGuardView,
  currentIndex: currentViewIndex,
  selectView: selectGuardView,
  nextView: nextGuardView,
  prevView: prevGuardView,
  setViews: setGuardViews,
  handleKeyDown: handleGuardKey,
} = useGuardViews([], '+z')

const guardViews = computed<string[]>(() => {
  if (!latestRun.value) return []
  return latestRun.value.guard_views || latestRun.value.report_json?.guard_views || []
})

watch(
  guardViews,
  (views) => {
    setGuardViews(views)
  },
  { immediate: true }
)

const guardImageUrl = computed(() => {
  if (!latestRun.value) return ''
  return getGuardImageUrl(latestRun.value.id, currentGuardView.value)
})

watch(currentGuardView, () => {
  imgError.value = false
})

function formatViewName(v: string): string {
  const map: Record<string, string> = {
    '+x': '+X (East)',
    '-x': '-X (West)',
    '+y': '+Y (North)',
    '-y': '-Y (South)',
    '+z': '+Z (Top)',
    '-z': '-Z (Bottom)',
  }
  return map[v] || v
}

const { layers, handleKeyDown } = useLayers()

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

  viewA.onPick = async (faceId, point) => {
    pickedFace.value = { viewKind: 'before', faceId, point, loading: true }
    if (snapshotVersion.value) {
      try {
        const details = await fetchFace(snapshotVersion.value.id, faceId)
        if (pickedFace.value && pickedFace.value.faceId === faceId && pickedFace.value.viewKind === 'before') {
          pickedFace.value.details = details
          pickedFace.value.loading = false
        }
      } catch (err: any) {
        if (pickedFace.value && pickedFace.value.faceId === faceId && pickedFace.value.viewKind === 'before') {
          pickedFace.value.error = err.message || 'Failed to fetch face'
          pickedFace.value.loading = false
        }
      }
    } else {
      pickedFace.value.loading = false
    }
  }
  viewB.onPick = async (faceId, point) => {
    pickedFace.value = { viewKind: 'after', faceId, point, loading: true }
    if (fixedVersion.value) {
      try {
        const details = await fetchFace(fixedVersion.value.id, faceId)
        if (pickedFace.value && pickedFace.value.faceId === faceId && pickedFace.value.viewKind === 'after') {
          pickedFace.value.details = details
          pickedFace.value.loading = false
        }
      } catch (err: any) {
        if (pickedFace.value && pickedFace.value.faceId === faceId && pickedFace.value.viewKind === 'after') {
          pickedFace.value.error = err.message || 'Failed to fetch face'
          pickedFace.value.loading = false
        }
      }
    } else {
      pickedFace.value.loading = false
    }
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
    // If a fixed version exists, try to load source_faces to highlight hidden faces in BEFORE
    if (fixedVersion.value && viewA && snapshotVersion.value) {
      try {
        const res = await fetch(`/api/versions/${fixedVersion.value.id}/assets/source_faces.json`)
        if (res.ok) {
          const sf: number[][] = await res.json()
          const kept = new Set(sf.flat())
          const nSnap = snapshotVersion.value.tri_count || 0
          const deleted: number[] = []
          for (let f = 0; f < nSnap; f++) {
            if (!kept.has(f)) deleted.push(f)
          }
          viewA.setHiddenFaces(deleted)
        }
      } catch {
        // Assets not available or fetch failed
      }
    }
    updateLayers()
  } catch (err: any) {
    console.error('Failed loading models:', err)
  }
}

function updateLayers() {
  if (viewA) {
    viewA.setLayer('grid', layers.grid)
    viewA.setLayer('outline', layers.outline)
    viewA.setLayer('tri', layers.tri)
    viewA.setLayer('creases', layers.creases)
    viewA.setLayer('hidden', layers.hidden)
    viewA.setXRay(layers.xray)
    viewA.setOnesidedDiagnostic(layers.onesided)
  }
  if (viewB) {
    viewB.setLayer('grid', layers.grid)
    viewB.setLayer('outline', layers.outline)
    viewB.setLayer('tri', layers.tri)
    viewB.setLayer('creases', layers.creases)
    viewB.setLayer('hidden', layers.hidden)
    viewB.setXRay(layers.xray)
    viewB.setOnesidedDiagnostic(layers.onesided)
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
    latestRun.value = {
      id: 0,
      version_id: snapshotVersion.value.id,
      status: 'failed',
      error: err.message || 'Fix execution failed',
      created_at: new Date().toISOString(),
    }
    alert(`Fix failed: ${err.message}`)
  } finally {
    fixing.value = false
  }
}

function onImageError() {
  imgError.value = true
}

function onGlobalKeyDown(e: KeyboardEvent) {
  if (showGuardModal.value) {
    if (e.key === 'Escape') {
      showGuardModal.value = false
      return
    }
    handleGuardKey(e)
    return
  }
  handleKeyDown(e)
}

onMounted(() => {
  initWorkspace()
  window.addEventListener('keydown', onGlobalKeyDown)
  watch(
    () => ({ ...layers }),
    () => {
      updateLayers()
      toggleSync()
    },
    { deep: true }
  )
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKeyDown)
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

.kbd-hint {
  font-size: 10px;
  background: #eaecef;
  border: 1px solid #d0d7de;
  border-radius: 3px;
  padding: 0 4px;
  color: #57606a;
  font-family: ui-monospace, monospace;
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

.modal-title-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
}

.modal-header h3 {
  margin: 0;
  font-size: 15px;
}

.view-indicator {
  font-size: 12px;
  color: #6a737d;
}

.modal-views-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 18px;
  background: #fafbfc;
  border-bottom: 1px solid #eee;
}

.views-chips {
  display: flex;
  gap: 6px;
  flex: 1;
  overflow-x: auto;
}

.btn-arrow {
  background: #fff;
  border: 1px solid #dcdde2;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}
.btn-arrow:hover {
  background: #f0f1f4;
}

.btn-view {
  background: #f0f1f4;
  border: 1px solid #dcdde2;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
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

.empty-guard-state {
  padding: 40px 20px;
  background: #fcfcfd;
  border: 1px dashed #d0d7de;
  border-radius: 6px;
  color: #57606a;
}
.empty-guard-state p {
  margin: 4px 0;
}
.text-hint {
  font-size: 12px;
  color: #8c959f;
}
</style>
