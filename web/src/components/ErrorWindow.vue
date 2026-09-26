<template>
  <div ref="el" class="window" :style="{ left: pos.x + 'px', top: pos.y + 'px' }">
    <div class="title-bar" @pointerdown="startDrag" @pointermove="onDrag" @pointerup="stopDrag">
      <span class="swatch" :style="{ background: color }"></span>
      <span class="title-text">{{ title }}</span>
      <button type="button" class="close-btn" @click="emit('close')">&times;</button>
    </div>

    <div class="body">
      <template v-if="kind">
        <h3>What it is</h3>
        <p>{{ kind.what }}</p>

        <h3>How we find it</h3>
        <ol>
          <li v-for="(step, i) in kind.find" :key="i">{{ step }}</li>
        </ol>

        <h3>Why the model has it</h3>
        <p>{{ kind.why }}</p>
        <p v-if="kind.why_note" class="note">{{ kind.why_note }}</p>

        <h3>How much of each model it is</h3>
        <table class="model-table">
          <tbody>
            <tr v-for="modelId in Object.keys(kind.models)" :key="modelId">
              <td>{{ modelName(modelId) }}</td>
              <td><span class="status-badge" :class="'status-' + kind.models[modelId].status">{{ statusLabel(kind.models[modelId].status) }}</span></td>
              <td>{{ kind.models[modelId].count }}</td>
            </tr>
          </tbody>
        </table>

        <h3>Why you don't want it in Unity</h3>
        <ul>
          <li v-for="(item, i) in kind.unity" :key="i">{{ item }}</li>
        </ul>

        <h3>The solution</h3>
        <ol>
          <li v-for="(step, i) in kind.solution" :key="i">{{ step }}</li>
        </ol>
        <template v-if="kind.never && kind.never.length">
          <h4>Never do this</h4>
          <ul>
            <li v-for="(item, i) in kind.never" :key="i">{{ item }}</li>
          </ul>
        </template>

        <h3>Done so far</h3>
        <ul>
          <li v-for="(item, i) in kind.done" :key="i">{{ item }}</li>
        </ul>

        <h3>Why some can remain</h3>
        <p>{{ kind.remain }}</p>

        <h3>Your screenshots</h3>
        <div v-if="kind.examples.length" class="examples-grid">
          <figure v-for="(ex, i) in kind.examples" :key="i" class="example" @click="onImageClick(ex.image)">
            <img v-if="ex.image" :src="imageUrl(ex.image)" :alt="ex.caption || ex.words || ''" />
            <figcaption>
              <span v-if="ex.date" class="ex-date">{{ ex.date }}</span>
              <span v-if="ex.words" class="ex-words">&ldquo;{{ ex.words }}&rdquo;</span>
              <span v-if="ex.caption" class="ex-caption">{{ ex.caption }}</span>
            </figcaption>
          </figure>
        </div>
        <p v-else class="note">None yet.</p>

        <h3>Your verdict</h3>
        <div v-for="modelId in Object.keys(kind.models)" :key="modelId" class="verdict-row">
          <div class="verdict-row-head">
            <span class="model-id">{{ modelId }}</span>
            <button
              v-for="v in VERDICTS"
              :key="v.id"
              type="button"
              class="verdict-btn"
              :class="{ active: currentVerdict(modelId) === v.id }"
              @click="toggleVerdict(modelId, v.id)"
            >{{ v.label }}</button>
          </div>
          <textarea
            class="verdict-note"
            :value="noteFor(modelId)"
            placeholder="Note (optional)"
            @blur="onNoteBlur(modelId, $event)"
          ></textarea>
          <div class="verdict-foot">
            <span v-if="verdictOf(validation, kind.id, modelId)" class="verdict-saved">saved {{ verdictOf(validation, kind.id, modelId)!.at }}</span>
            <span v-if="saveError[modelId]" class="verdict-error">{{ saveError[modelId] }}</span>
          </div>
        </div>

        <h3>Engine files</h3>
        <p class="tags">
          <code v-for="f in kind.engine_files" :key="f" class="tag">{{ f }}</code>
        </p>
        <h4>Numbers from</h4>
        <p class="note">
          <span v-for="(s, i) in kind.sources" :key="i">{{ s }}<template v-if="i < kind.sources.length - 1">; </template></span>
        </p>
      </template>

      <template v-else-if="mistake">
        <h3>What happened</h3>
        <p>{{ mistake.what_happened }}</p>

        <h3>How it was caught</h3>
        <p>{{ mistake.how_caught }}</p>

        <h3>The fix</h3>
        <p>{{ mistake.fix }}</p>

        <h3>Engine files</h3>
        <p class="tags">
          <code v-for="f in mistake.engine_files" :key="f" class="tag">{{ f }}</code>
        </p>

        <h3>Commits</h3>
        <p v-if="!mistake.commits || !mistake.commits.length" class="note">None recorded.</p>
        <p v-else class="tags">
          <code v-for="c in mistake.commits" :key="c" class="tag">{{ c }}</code>
        </p>

        <h3>Your screenshots</h3>
        <div v-if="mistake.examples.length" class="examples-grid">
          <figure v-for="(ex, i) in mistake.examples" :key="i" class="example" @click="onImageClick(ex.image)">
            <img v-if="ex.image" :src="imageUrl(ex.image)" :alt="ex.caption || ex.words || ''" />
            <figcaption>
              <span v-if="ex.date" class="ex-date">{{ ex.date }}</span>
              <span v-if="ex.words" class="ex-words">&ldquo;{{ ex.words }}&rdquo;</span>
              <span v-if="ex.caption" class="ex-caption">{{ ex.caption }}</span>
            </figcaption>
          </figure>
        </div>
        <p v-else class="note">None yet.</p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import {
  clampWindow, statusLabel, imageUrl, verdictOf, VERDICTS,
  type Kind, type EngineMistake, type ModelCard, type Validation, type Verdict, type Example,
} from '../utils/errorsDoc'

const props = defineProps<{
  kind: Kind | null
  mistake: EngineMistake | null
  models: ModelCard[]
  validation: Validation | null
}>()

const emit = defineEmits<{
  close: []
  image: [payload: { list: string[]; name: string }]
  verdict: [payload: { kindId: string; modelId: string; verdict: Verdict | null; note: string }]
}>()

const el = ref<HTMLElement | null>(null)
const pos = reactive({ x: 0, y: 0 })
const saveError = reactive<Record<string, string>>({})

const title = computed(() => props.kind?.title ?? props.mistake?.title ?? '')
const color = computed(() => props.kind?.color ?? '#374151')
const examples = computed<Example[]>(() => props.kind?.examples ?? props.mistake?.examples ?? [])

function modelName(id: string): string {
  return props.models.find(m => m.id === id)?.name ?? id
}

// --- dragging ---
let dragging = false
let offX = 0
let offY = 0

function startDrag(ev: PointerEvent) {
  dragging = true
  ;(ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId)
  offX = ev.clientX - pos.x
  offY = ev.clientY - pos.y
}
function onDrag(ev: PointerEvent) {
  if (!dragging) return
  const w = el.value?.offsetWidth ?? 560
  const clamped = clampWindow(ev.clientX - offX, ev.clientY - offY, w, window.innerWidth, window.innerHeight)
  pos.x = clamped.x
  pos.y = clamped.y
}
function stopDrag(ev: PointerEvent) {
  dragging = false
  ;(ev.currentTarget as HTMLElement).releasePointerCapture(ev.pointerId)
}

// --- images ---
function onImageClick(image: string | undefined) {
  if (!image) return
  const list = examples.value.map(e => e.image).filter((n): n is string => n !== undefined)
  emit('image', { list, name: image })
}

// --- verdicts ---
function currentVerdict(modelId: string): Verdict | null {
  if (!props.kind) return null
  return verdictOf(props.validation, props.kind.id, modelId)?.verdict ?? null
}
function noteFor(modelId: string): string {
  if (!props.kind) return ''
  return verdictOf(props.validation, props.kind.id, modelId)?.note ?? ''
}
function toggleVerdict(modelId: string, v: Verdict) {
  if (!props.kind) return
  const next: Verdict | null = currentVerdict(modelId) === v ? null : v
  emit('verdict', { kindId: props.kind.id, modelId, verdict: next, note: noteFor(modelId) })
}
function onNoteBlur(modelId: string, ev: FocusEvent) {
  if (!props.kind) return
  const value = (ev.target as HTMLTextAreaElement).value
  if (value === noteFor(modelId)) return
  const verdict = currentVerdict(modelId) ?? 'unsure'
  emit('verdict', { kindId: props.kind.id, modelId, verdict, note: value })
}

function setSaveError(modelId: string, message: string | null) {
  if (message === null) delete saveError[modelId]
  else saveError[modelId] = message
}
defineExpose({ setSaveError })

// --- lifecycle ---
function onKeydown(ev: KeyboardEvent) {
  if (ev.key === 'Escape') emit('close')
}
onMounted(() => {
  const start = clampWindow(window.innerWidth - 560 - 24, 72, 560, window.innerWidth, window.innerHeight)
  pos.x = start.x
  pos.y = start.y
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.window {
  position: fixed;
  z-index: 40;
  width: 560px;
  height: 72vh;
  min-width: 360px;
  min-height: 240px;
  resize: both;
  overflow: hidden;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #dcdde2;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  display: flex;
  flex-direction: column;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #1c1d21;
}

.title-bar {
  height: 48px;
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 0 14px;
  cursor: move;
  touch-action: none;
  user-select: none;
  border-bottom: 1px solid #dcdde2;
  background: #fafbfc;
  border-radius: 8px 8px 0 0;
}

.swatch {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  flex-shrink: 0;
}

.title-text {
  flex: 1;
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.close-btn {
  border: none;
  background: transparent;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  color: #676b75;
  padding: 4px 8px;
  border-radius: 4px;
}
.close-btn:hover {
  background: #eceef2;
  color: #1c1d21;
}

.body {
  flex: 1;
  overflow: auto;
  padding: 14px 20px 24px;
  font-size: 14px;
  line-height: 1.5;
  word-wrap: break-word;
}

.body h3 {
  font-size: 14px;
  margin: 18px 0 6px;
  border-top: 1px solid #eceef2;
  padding-top: 14px;
}
.body h3:first-child {
  margin-top: 0;
  border-top: none;
  padding-top: 0;
}
.body h4 {
  font-size: 13px;
  margin: 10px 0 4px;
  color: #676b75;
}

.body p, .body ul, .body ol {
  margin: 4px 0;
}
.body ul, .body ol {
  padding-left: 22px;
}

.note {
  color: #676b75;
  font-style: italic;
  font-size: 13px;
}

.model-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.model-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #eceef2;
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

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  background: #f0f1f4;
  border: 1px solid #dcdde2;
  border-radius: 4px;
  padding: 2px 6px;
}

.examples-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}
.example {
  margin: 0;
  cursor: pointer;
  border: 1px solid #dcdde2;
  border-radius: 6px;
  overflow: hidden;
  background: #fafbfc;
}
.example img {
  width: 100%;
  height: 90px;
  object-fit: cover;
  display: block;
}
.example figcaption {
  padding: 6px 8px;
  font-size: 11px;
  color: #444;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ex-date {
  color: #676b75;
}

.verdict-row {
  border: 1px solid #eceef2;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
}
.verdict-row-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.model-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-weight: 600;
  font-size: 12px;
  margin-right: 4px;
}
.verdict-btn {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 5px;
  border: 1px solid #d0d2d7;
  background: #f0f1f4;
  color: #222;
  cursor: pointer;
}
.verdict-btn.active {
  background: #1f5bff;
  border-color: #1f5bff;
  color: #fff;
}
.verdict-note {
  width: 100%;
  margin-top: 6px;
  font-size: 12px;
  font-family: inherit;
  border: 1px solid #d0d2d7;
  border-radius: 5px;
  padding: 6px 8px;
  resize: vertical;
  min-height: 32px;
}
.verdict-foot {
  display: flex;
  gap: 10px;
  margin-top: 4px;
  font-size: 11px;
}
.verdict-saved {
  color: #676b75;
}
.verdict-error {
  color: #b3261e;
  font-weight: 600;
}
</style>
