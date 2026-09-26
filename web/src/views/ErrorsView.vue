<template>
  <div class="errors-container">
    <header class="page-header">
      <div class="header-left">
        <router-link to="/" class="back-link">&larr; Models</router-link>
        <h1>Errors: what they are, and the plan</h1>
        <p v-if="catalogue" class="built-from">Built from commit <code>{{ catalogue.built_from.commit }}</code>, {{ catalogue.built_from.date }}</p>
      </div>
      <div v-if="summary" class="validation-summary">
        Validated {{ summary.validated }} of {{ summary.pairs }} &middot; {{ summary.error }} must fix &middot; {{ summary.ok }} OK &middot; {{ summary.unsure }} not sure
      </div>
    </header>

    <main class="page-content">
      <div v-if="saveBanner" class="banner banner-error banner-save">
        <span>{{ saveBanner }}</span>
        <button type="button" class="banner-dismiss" @click="dismissSaveBanner">&times;</button>
      </div>
      <div v-if="loadError" class="banner banner-error">{{ loadError }}</div>
      <div v-else-if="loading" class="loading-state">Loading&hellip;</div>

      <template v-if="catalogue">
        <section class="origin">
          <p v-for="(p, i) in catalogue.origin" :key="i">{{ p }}</p>
        </section>

        <p v-if="validationError" class="banner-note">Verdicts could not be loaded</p>

        <section class="models-grid">
          <div v-for="m in catalogue.models" :key="m.id" class="model-card">
            <h3>{{ m.name }} <span class="model-id-tag">{{ m.id }}</span></h3>
            <p class="model-role">{{ m.role }}</p>
            <ul class="model-numbers">
              <li v-for="key in Object.keys(m.numbers)" :key="key">
                <span class="num-label">{{ numberLabel(key) }}:</span>
                <span class="num-value">{{ numberValue(m.numbers[key]) }}</span>
              </li>
            </ul>
            <p class="model-source">{{ m.source }}</p>
            <div v-if="m.skp" class="model-skp">
              <code>{{ m.skp }}</code>
              <button type="button" class="btn-copy" @click="copySkp(m.id, m.skp)">{{ copiedModel === m.id ? 'Copied!' : 'Copy' }}</button>
            </div>
          </div>
        </section>

        <section class="filter-bar">
          <label class="filter-field">
            Model
            <select v-model="filter.model">
              <option :value="null">All</option>
              <option v-for="mc in choices.models" :key="mc.id" :value="mc.id">{{ mc.label }}</option>
            </select>
          </label>
          <label class="filter-field">
            Engine file
            <select v-model="filter.engine">
              <option :value="null">All</option>
              <option v-for="f in choices.engineFiles" :key="f" :value="f">{{ f }}</option>
            </select>
          </label>
          <span class="filter-count">{{ filteredKinds.length }} of {{ catalogue.kinds.length }} kinds</span>
          <button type="button" class="btn-clear" @click="clearFilter">Clear</button>
        </section>

        <section class="kinds-grid">
          <article
            v-for="k in filteredKinds"
            :key="k.id"
            class="kind-card"
            role="button"
            tabindex="0"
            :style="{ borderLeftColor: k.color }"
            @click="openWindow(k.id)"
            @keydown.enter="openWindow(k.id)"
          >
            <h3>{{ k.title }}</h3>
            <p class="kind-summary">{{ k.summary }}</p>
            <div v-for="modelId in Object.keys(k.models)" :key="modelId" class="kind-model-row">
              <span class="model-id-tag">{{ modelId }}</span>
              <span class="status-badge" :class="'status-' + k.models[modelId].status">{{ statusLabel(k.models[modelId].status) }}</span>
              <span class="kind-count">{{ k.models[modelId].count }}</span>
              <span
                v-if="verdictOf(validation, k.id, modelId)"
                class="verdict-badge"
                :class="'verdict-' + verdictOf(validation, k.id, modelId)!.verdict"
              >{{ verdictLabel(verdictOf(validation, k.id, modelId)!.verdict) }}</span>
            </div>
          </article>
        </section>

        <section class="mistakes-section">
          <h2>Engine mistakes caught by reviews</h2>
          <div class="mistakes-grid">
            <article
              v-for="m in filteredMistakes"
              :key="m.id"
              class="mistake-card"
              role="button"
              tabindex="0"
              @click="openWindow(m.id)"
              @keydown.enter="openWindow(m.id)"
            >
              <h3>{{ m.title }}</h3>
              <p class="mistake-models">{{ m.models.join(', ') }}</p>
            </article>
          </div>
        </section>

        <section class="other-screenshots">
          <h2>Other screenshots you sent</h2>
          <div class="screenshots-strip">
            <figure
              v-for="(ex, i) in catalogue.other_screenshots"
              :key="i"
              class="screenshot"
              @click="openOtherLightbox(ex.image)"
            >
              <img v-if="ex.image" :src="imageUrl(ex.image)" :alt="ex.caption || ''" />
              <figcaption>{{ ex.caption }}</figcaption>
            </figure>
          </div>
        </section>
      </template>
    </main>

    <ErrorWindow
      v-if="openKind || openMistake"
      :key="openId ?? ''"
      ref="windowRef"
      :kind="openKind"
      :mistake="openMistake"
      :models="catalogue ? catalogue.models : []"
      :validation="validation"
      :verdicts-ready="!validationError"
      @close="closeWindow"
      @image="onWindowImage"
      @verdict="saveVerdict"
    />

    <div v-if="lightbox" class="lightbox" @click.self="lightbox = null">
      <button type="button" class="lightbox-close" @click="lightbox = null">&times;</button>
      <button v-if="lightbox.list.length > 1" type="button" class="lightbox-nav lightbox-prev" @click="stepLightbox(-1)">&lsaquo;</button>
      <img class="lightbox-img" :src="imageUrl(lightbox.list[lightbox.index])" alt="" />
      <button v-if="lightbox.list.length > 1" type="button" class="lightbox-nav lightbox-next" @click="stepLightbox(1)">&rsaquo;</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ErrorWindow from '../components/ErrorWindow.vue'
import {
  filterKinds, filterMistakes, filterChoices, filterFromQuery, openFromQuery, filterToQuery,
  statusLabel, imageUrl, verdictOf, validationSummary, VERDICTS,
  type Catalogue, type Kind, type EngineMistake, type DocFilter, type Validation, type Verdict, type VerdictEntry,
} from '../utils/errorsDoc'

const route = useRoute()
const router = useRouter()

const catalogue = ref<Catalogue | null>(null)
const validation = ref<Validation | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)
const validationError = ref(false)
const ready = ref(false)

const filter = reactive<DocFilter>({ model: null, engine: null })
const openId = ref<string | null>(null)
const windowRef = ref<InstanceType<typeof ErrorWindow> | null>(null)
const copiedModel = ref<string | null>(null)
const lightbox = ref<{ list: string[]; index: number } | null>(null)
const saveBanner = ref<string | null>(null)

function dismissSaveBanner() {
  saveBanner.value = null
}

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

const summary = computed(() => (catalogue.value ? validationSummary(catalogue.value, validation.value) : null))
const choices = computed(() => (catalogue.value ? filterChoices(catalogue.value) : { models: [], engineFiles: [] }))
const filteredKinds = computed(() => (catalogue.value ? filterKinds(catalogue.value.kinds, filter) : []))
const filteredMistakes = computed(() => (catalogue.value ? filterMistakes(catalogue.value.engine_mistakes, filter) : []))

const openKind = computed<Kind | null>(() => {
  if (!catalogue.value || !openId.value) return null
  return catalogue.value.kinds.find(k => k.id === openId.value) ?? null
})
const openMistake = computed<EngineMistake | null>(() => {
  if (!catalogue.value || !openId.value || openKind.value) return null
  return catalogue.value.engine_mistakes.find(m => m.id === openId.value) ?? null
})

function numberLabel(key: string): string {
  if (key === 'triangles') return 'Triangles'
  if (key === 'back_faces_px') return 'Back faces seen from outside (px)'
  return key
}
function numberValue(value: number | number[]): string {
  if (Array.isArray(value)) return `${value[0].toLocaleString()} → ${value[1].toLocaleString()}`
  return value.toLocaleString()
}
function verdictLabel(v: Verdict): string {
  return VERDICTS.find(x => x.id === v)?.label ?? v
}

async function copySkp(modelId: string, path: string | undefined) {
  if (!path) return
  try {
    await navigator.clipboard.writeText(path)
    copiedModel.value = modelId
    setTimeout(() => {
      if (copiedModel.value === modelId) copiedModel.value = null
    }, 2000)
  } catch {
    // clipboard unavailable; nothing more we can do
  }
}

function openWindow(id: string) {
  openId.value = id
}
function closeWindow() {
  openId.value = null
}

function onWindowImage(payload: { list: string[]; name: string }) {
  const idx = payload.list.indexOf(payload.name)
  lightbox.value = { list: payload.list, index: idx < 0 ? 0 : idx }
}

const otherImages = computed<string[]>(() =>
  (catalogue.value?.other_screenshots ?? []).map(e => e.image).filter((n): n is string => n !== undefined)
)
function openOtherLightbox(image: string | undefined) {
  if (!image) return
  const idx = otherImages.value.indexOf(image)
  lightbox.value = { list: otherImages.value, index: idx < 0 ? 0 : idx }
}
function stepLightbox(delta: number) {
  if (!lightbox.value) return
  const n = lightbox.value.list.length
  lightbox.value.index = (lightbox.value.index + delta + n) % n
}

function clearFilter() {
  filter.model = null
  filter.engine = null
}

const saveChains = new Map<string, Promise<void>>()

// Saves for the same kind/model are chained so a note-blur and a verdict click fired close
// together always reach the server in the order the owner made them, never racing.
function saveVerdict(payload: { kindId: string; modelId: string; verdict: Verdict | null; note: string }): Promise<void> {
  const key = `${payload.kindId}/${payload.modelId}`
  const chained = (saveChains.get(key) ?? Promise.resolve()).then(() => doSaveVerdict(payload))
  saveChains.set(key, chained)
  return chained
}

async function doSaveVerdict(payload: { kindId: string; modelId: string; verdict: Verdict | null; note: string }) {
  try {
    const res = await fetch(
      `/api/docs/validation/${encodeURIComponent(payload.kindId)}/${encodeURIComponent(payload.modelId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ verdict: payload.verdict, note: payload.note }),
      }
    )
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const data = await res.json()
        if (res.status === 422 && Array.isArray(data?.detail) && data.detail[0]?.msg) {
          detail = data.detail[0].msg
        } else if (typeof data?.detail === 'string') {
          detail = data.detail
        }
      } catch {
        // keep default detail
      }
      throw new Error(detail)
    }
    const data = (await res.json()) as { kind: string; model: string; entry: VerdictEntry | null }
    if (!validation.value) validation.value = { version: 1, verdicts: {} }
    if (data.entry) {
      if (!validation.value.verdicts[data.kind]) validation.value.verdicts[data.kind] = {}
      validation.value.verdicts[data.kind][data.model] = data.entry
    } else if (validation.value.verdicts[data.kind]) {
      delete validation.value.verdicts[data.kind][data.model]
      if (Object.keys(validation.value.verdicts[data.kind]).length === 0) {
        delete validation.value.verdicts[data.kind]
      }
    }
    if (openId.value === payload.kindId) {
      windowRef.value?.setSaveError(payload.modelId, null)
    }
  } catch (err) {
    if (openId.value === payload.kindId) {
      windowRef.value?.setSaveError(payload.modelId, `Not saved: ${errMsg(err)}`)
    } else {
      const title = catalogue.value?.kinds.find(k => k.id === payload.kindId)?.title ?? payload.kindId
      saveBanner.value = `Not saved: ${title} — ${payload.modelId}: ${errMsg(err)}`
    }
  }
}

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const res = await fetch('/docs/errors.json', { cache: 'no-cache' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    catalogue.value = (await res.json()) as Catalogue
  } catch (err) {
    loadError.value = `Could not load the documentation: ${errMsg(err)}`
  } finally {
    loading.value = false
  }

  try {
    const res = await fetch('/api/docs/validation')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    validation.value = (await res.json()) as Validation
  } catch {
    validationError.value = true
  }

  if (catalogue.value) {
    const f = filterFromQuery(route.query, catalogue.value)
    filter.model = f.model
    filter.engine = f.engine
    openId.value = openFromQuery(route.query, catalogue.value)
  }
  ready.value = true
}

watch(
  () => [filter.model, filter.engine, openId.value] as const,
  () => {
    if (!ready.value) return
    router.replace({ query: filterToQuery({ model: filter.model, engine: filter.engine }, openId.value) })
  }
)

function onKeydown(ev: KeyboardEvent) {
  if (!lightbox.value) return
  if (ev.key === 'Escape') {
    ev.stopImmediatePropagation()
    lightbox.value = null
  } else if (ev.key === 'ArrowLeft') {
    ev.stopImmediatePropagation()
    stepLightbox(-1)
  } else if (ev.key === 'ArrowRight') {
    ev.stopImmediatePropagation()
    stepLightbox(1)
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  load()
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.errors-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 16px 60px;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #1c1d21;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  border-bottom: 1px solid #dcdde2;
  padding-bottom: 16px;
  margin-bottom: 24px;
  flex-wrap: wrap;
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

.header-left h1 {
  margin: 6px 0 4px;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.built-from {
  margin: 0;
  font-size: 12px;
  color: #676b75;
}
.built-from code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.validation-summary {
  font-size: 13px;
  color: #444;
  background: #f0f1f4;
  border: 1px solid #dcdde2;
  border-radius: 6px;
  padding: 8px 12px;
  white-space: nowrap;
  align-self: center;
}

.banner {
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 20px;
  font-size: 14px;
}
.banner-error {
  background: #fde8e8;
  color: #b3261e;
  border: 1px solid #f5c2c2;
}
.banner-note {
  color: #8a6d0d;
  font-size: 13px;
  margin: 0 0 16px;
}
.banner-save {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.banner-dismiss {
  border: none;
  background: transparent;
  color: inherit;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
  flex-shrink: 0;
}

.loading-state {
  color: #676b75;
  padding: 20px 0;
}

.origin p {
  color: #333;
  line-height: 1.6;
  margin: 0 0 10px;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin: 20px 0 28px;
}

.model-card {
  background: #fff;
  border: 1px solid #dcdde2;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  min-width: 0;
}
.model-card h3 {
  margin: 0 0 4px;
  font-size: 15px;
  overflow-wrap: anywhere;
}
.model-id-tag {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  color: #676b75;
  background: #f0f1f4;
  border-radius: 4px;
  padding: 1px 5px;
}
.model-role {
  color: #676b75;
  font-size: 13px;
  margin: 0 0 10px;
}
.model-numbers {
  list-style: none;
  padding: 0;
  margin: 0 0 8px;
  font-size: 13px;
}
.model-numbers li {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 3px 0;
  border-bottom: 1px solid #f0f1f4;
}
.num-label {
  color: #676b75;
}
.num-value {
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.model-source {
  font-size: 12px;
  color: #676b75;
  margin: 8px 0 0;
  overflow-wrap: anywhere;
}
.model-skp {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  background: #fafbfc;
  border: 1px solid #eceef2;
  border-radius: 6px;
  padding: 6px 8px;
}
.model-skp code {
  flex: 1;
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.btn-copy {
  flex-shrink: 0;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 5px;
  border: 1px solid #d0d2d7;
  background: #f0f1f4;
  color: #222;
  cursor: pointer;
}
.btn-copy:hover {
  background: #e4e6eb;
}

.filter-bar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  background: #f3f3f5;
  border: 1px solid #dcdde2;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 20px;
}
.filter-field {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #444;
}
.filter-field select {
  font-size: 13px;
  padding: 4px 6px;
  border-radius: 5px;
  border: 1px solid #d0d2d7;
  background: #fff;
  max-width: 260px;
}
.filter-count {
  font-size: 13px;
  color: #676b75;
  margin-left: auto;
}
.btn-clear {
  font-size: 12px;
  padding: 5px 10px;
  border-radius: 5px;
  border: 1px solid #d0d2d7;
  background: #f0f1f4;
  color: #222;
  cursor: pointer;
}
.btn-clear:hover {
  background: #e4e6eb;
}

.kinds-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}
.kind-card {
  background: #fff;
  border: 1px solid #dcdde2;
  border-left: 6px solid #1f5bff;
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  text-align: left;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  min-width: 0;
}
.kind-card:hover {
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1);
}
.kind-card:focus-visible {
  outline: 2px solid #1f5bff;
  outline-offset: 2px;
}
.kind-card h3 {
  margin: 0 0 6px;
  font-size: 15px;
}
.kind-summary {
  color: #444;
  font-size: 13px;
  margin: 0 0 10px;
  line-height: 1.4;
}
.kind-model-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  border-top: 1px solid #f0f1f4;
}
.kind-count {
  color: #676b75;
  flex: 1;
  overflow-wrap: anywhere;
}

.status-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f0f1f4;
  color: #444;
  white-space: nowrap;
}
.status-fixed { background: #e6f8ee; color: #0d8a43; }
.status-partly { background: #fff3cd; color: #8a6d0d; }
.status-open { background: #fde8e8; color: #b3261e; }
.status-planned { background: #eef3ff; color: #1f5bff; }

.verdict-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
}
.verdict-error { background: #fde8e8; color: #b3261e; }
.verdict-ok { background: #e6f8ee; color: #0d8a43; }
.verdict-unsure { background: #f0f1f4; color: #676b75; }

.mistakes-section h2,
.other-screenshots h2 {
  font-size: 17px;
  margin: 0 0 14px;
}
.mistakes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
  margin-bottom: 32px;
}
.mistake-card {
  background: #fff;
  border: 1px solid #dcdde2;
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  text-align: left;
}
.mistake-card:hover {
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1);
}
.mistake-card h3 {
  margin: 0 0 6px;
  font-size: 14px;
}
.mistake-models {
  font-size: 12px;
  color: #676b75;
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.screenshots-strip {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.screenshot {
  width: 160px;
  margin: 0;
  cursor: pointer;
  border: 1px solid #dcdde2;
  border-radius: 6px;
  overflow: hidden;
  background: #fafbfc;
}
.screenshot img {
  width: 100%;
  height: 100px;
  object-fit: cover;
  display: block;
}
.screenshot figcaption {
  font-size: 11px;
  color: #444;
  padding: 6px 8px;
}

.lightbox {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: rgba(10, 10, 12, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
}
.lightbox-img {
  max-width: 88vw;
  max-height: 86vh;
  object-fit: contain;
}
.lightbox-close {
  position: absolute;
  top: 18px;
  right: 24px;
  font-size: 28px;
  line-height: 1;
  background: transparent;
  border: none;
  color: #fff;
  cursor: pointer;
}
.lightbox-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  font-size: 36px;
  line-height: 1;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  color: #fff;
  cursor: pointer;
  padding: 8px 16px;
  border-radius: 6px;
}
.lightbox-prev { left: 18px; }
.lightbox-next { right: 18px; }
</style>
