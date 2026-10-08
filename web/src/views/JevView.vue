<template>
  <div class="jev-container">
    <header class="page-header">
      <router-link to="/" class="back-link">&larr; Models</router-link>
      <h1>Jev: review suggestions</h1>
    </header>

    <main class="page-content">
      <div v-if="serviceBanner" class="banner banner-info" role="status">{{ serviceBanner }}</div>

      <template v-else>
        <div v-if="loadError" class="banner banner-error" role="alert">{{ loadError }}</div>
        <div v-if="health && !health.jev_enabled" class="banner banner-info" role="status">
          Jev is off until the repair engine is ready
        </div>

        <nav class="tabs" aria-label="Question groups">
          <button
            v-for="t in TABS"
            :key="t.key"
            type="button"
            class="tab"
            :class="{ active: t.key === tabKey, disabled: !t.available }"
            :aria-pressed="t.key === tabKey"
            :disabled="!t.available"
            @click="selectTab(t.key)"
          >
            {{ t.label }}<span v-if="!t.available" class="tab-note"> (not available yet)</span>
          </button>
        </nav>

        <p v-if="!tab.available" class="not-available">Not available yet</p>

        <template v-else>
          <section class="counts" role="status">
            <span class="count count-pending">{{ counts.pending }} pending</span>
            <span class="count count-accepted">{{ counts.accepted }} accepted</span>
            <span class="count count-changed">{{ counts.changed }} changed</span>
            <span v-if="truncated" class="count-note">
              Showing the first {{ PAGE_LIMIT }} matches of a question type; narrow the filters to see the rest
            </span>
          </section>

          <section class="filter-bar">
            <label class="filter-field">
              Question
              <select v-model="qtype" @change="load">
                <option value="">All of this tab</option>
                <option v-for="q in tab.qtypes" :key="q" :value="q">{{ q }}</option>
              </select>
            </label>
            <label class="filter-field">
              Status
              <select v-model="filter.status">
                <option value="all">All</option>
                <option value="pending">Pending</option>
                <option value="accepted">Accepted</option>
                <option value="changed">Changed</option>
              </select>
            </label>
            <label class="filter-field">
              Min confidence
              <input v-model.number="filter.minConf" type="number" min="0" max="1" step="0.05" />
            </label>
            <label class="filter-field">
              Search
              <input v-model="filter.text" type="search" placeholder="subject" />
            </label>
            <span class="filter-count">{{ shown.length }} shown</span>
          </section>
          <p v-if="!minConfOk" class="field-hint" role="alert">Enter a minimum confidence between 0 and 1.</p>

          <section class="accept-all">
            <label class="filter-field">
              Accept all shown &ge;
              <input v-model.number="acceptMin" type="number" min="0" max="1" step="0.05" />
            </label>
            <button type="button" class="btn" :disabled="busy || !selection.length" @click="acceptAll">
              Accept {{ selection.length }}
            </button>
            <span v-if="notice" class="notice" role="status">{{ notice }}</span>
          </section>

          <div v-if="loading" class="loading-state" aria-live="polite">Loading&hellip;</div>
          <p v-else-if="!shown.length" class="empty">No suggestions for this filter.</p>

          <ul class="rows">
            <li v-for="r in shown" :key="r.id" class="row" :class="'status-' + r.status">
              <div class="row-main">
                <div class="row-title">
                  <strong>{{ r.subject }}</strong>
                  <span class="qtype">{{ r.qtype }}</span>
                  <span class="status-badge">{{ r.status }}</span>
                </div>
                <div v-if="textureName(r)" class="texture">Texture: <code>{{ textureName(r) }}</code></div>
                <details class="question">
                  <summary>Question</summary>
                  <p>{{ r.question.instructions }}</p>
                </details>
                <div class="answer">
                  Jev says <strong>{{ answerLabel(r.question, r.answer) }}</strong>
                  <span v-if="r.status !== 'pending'">
                    &middot; owner: <strong>{{ answerLabel(r.question, r.owner_answer) }}</strong>
                  </span>
                </div>
                <div class="confidence" :title="percent(r.confidence)">
                  <div class="bar"><div class="bar-fill" :style="{ width: percent(r.confidence) }"></div></div>
                  <span class="bar-label">{{ percent(r.confidence) }}</span>
                </div>
                <div v-if="alternatives(r).length" class="alternatives">
                  Other:
                  <span v-for="a in alternatives(r)" :key="String(a.value)" class="alt">
                    {{ a.label }} {{ percent(a.probability) }}
                  </span>
                </div>
                <div v-if="rowError[r.id]" class="row-error" role="alert">{{ rowError[r.id] }}</div>
              </div>

              <div class="row-actions">
                <button
                  v-if="r.status === 'pending'"
                  type="button"
                  class="btn"
                  :disabled="busy"
                  :aria-label="'Accept ' + r.subject"
                  @click="accept(r)"
                >
                  Accept
                </button>
                <select
                  :value="''"
                  :disabled="busy"
                  :aria-label="'Change ' + r.subject"
                  @change="change(r, $event)"
                >
                  <option value="">Change&hellip;</option>
                  <option v-for="(label, i) in optionLabels(r.question)" :key="i" :value="String(i)">{{ label }}</option>
                </select>
                <button
                  v-if="health && health.jev_enabled && r.status === 'pending'"
                  type="button"
                  class="btn"
                  :disabled="busy"
                  :aria-label="'Re-ask Jev about ' + r.subject"
                  @click="reask(r)"
                >
                  Re-ask Jev
                </button>
              </div>
            </li>
          </ul>
        </template>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { fetchHealth, fetchSuggestions, reaskSuggestion, reviewSuggestion } from '../api/decide'
import { ApiError } from '../api/client'
import {
  TABS,
  acceptAllSelection,
  answerLabel,
  errorText,
  filterRows,
  serviceNote,
  isValidThreshold,
  mergeResults,
  optionLabels,
  optionValues,
  runAcceptAll,
  suggestionParams,
  textureName,
  topAlternatives,
  type Counts,
  type DecideHealth,
  type Suggestion,
} from '../utils/jevReview'

const PAGE_LIMIT = 500
const DEBOUNCE_MS = 300

const health = ref<DecideHealth | null>(null)
const serviceBanner = ref('')
const loadError = ref('')
const tabKey = ref(TABS[0].key)
const qtype = ref('')
const rows = ref<Suggestion[]>([])
const counts = ref<Counts>({ pending: 0, accepted: 0, changed: 0 })
const filter = reactive({ status: 'pending', minConf: 0, text: '' })
const acceptMin = ref(0.9)
const loading = ref(false)
const busy = ref(false)
const notice = ref('')
const truncated = ref(false)
const rowError = reactive<Record<number, string>>({})

const tab = computed(() => TABS.find((t) => t.key === tabKey.value) ?? TABS[0])
const minConfOk = computed(() => isValidThreshold(filter.minConf))
const shown = computed(() => filterRows(rows.value, filter))
const selection = computed(() => acceptAllSelection(shown.value, acceptMin.value))

function percent(p: number): string {
  return `${Math.round(p * 100)}%`
}

function alternatives(r: Suggestion) {
  return topAlternatives(r, 2)
}

// A newer load makes an older reply stale: the older one is dropped when it arrives.
let loadSeq = 0

async function load() {
  if (!tab.value.available) return
  const mine = ++loadSeq
  loadError.value = ''
  const types = qtype.value ? [qtype.value] : tab.value.qtypes
  const queries = types.map((type) => suggestionParams(filter, type, PAGE_LIMIT))
  if (queries.some((q) => q === null)) {
    rows.value = []
    truncated.value = false
    loading.value = false
    return
  }
  loading.value = true
  try {
    const replies = await Promise.all(queries.map((q) => fetchSuggestions(q!)))
    if (mine !== loadSeq) return
    const merged = mergeResults(replies)
    rows.value = merged.items
    counts.value = merged.counts
    truncated.value = replies.some((r) => r.items.length >= PAGE_LIMIT)
  } catch (err) {
    if (mine !== loadSeq) return
    const note = serviceNote(err)
    if (note) serviceBanner.value = note
    else loadError.value = errorText(err)
  } finally {
    if (mine === loadSeq) loading.value = false
  }
}

// Status reloads at once; the text and the confidence wait until typing stops.
let timer: ReturnType<typeof setTimeout> | undefined
watch(
  () => filter.status,
  () => void load()
)
watch(
  () => [filter.minConf, filter.text],
  () => {
    clearTimeout(timer)
    timer = setTimeout(() => void load(), DEBOUNCE_MS)
  }
)
onBeforeUnmount(() => clearTimeout(timer))

function selectTab(key: string) {
  tabKey.value = key
  qtype.value = ''
  rows.value = []
  void load()
}

function applyRow(updated: Suggestion) {
  const i = rows.value.findIndex((r) => r.id === updated.id)
  if (i >= 0) rows.value[i] = updated
}

async function accept(r: Suggestion) {
  busy.value = true
  delete rowError[r.id]
  try {
    applyRow(await reviewSuggestion(r.id, { accept: true }))
    await load()
  } catch (err) {
    rowError[r.id] = errorText(err)
  } finally {
    busy.value = false
  }
}

async function change(r: Suggestion, event: Event) {
  const select = event.target as HTMLSelectElement
  if (select.value === '') return
  const index = Number(select.value)
  select.value = ''
  busy.value = true
  delete rowError[r.id]
  try {
    // the RAW value: true/false for Noul, the label for Choice, the int index for Score
    applyRow(await reviewSuggestion(r.id, { answer: optionValues(r.question)[index] }))
    await load()
  } catch (err) {
    rowError[r.id] = errorText(err)
  } finally {
    busy.value = false
  }
}

async function reask(r: Suggestion) {
  busy.value = true
  delete rowError[r.id]
  try {
    applyRow(await reaskSuggestion(r.id))
  } catch (err) {
    const text = errorText(err)
    rowError[r.id] = err instanceof ApiError && err.status === 409 ? `Re-ask refused: ${text}` : text
  } finally {
    busy.value = false
  }
}

async function acceptAll() {
  const ids = selection.value
  if (!ids.length) return
  if (!window.confirm(`Accept ${ids.length} suggestions with confidence of at least ${percent(acceptMin.value)}?`)) return
  busy.value = true
  notice.value = ''
  const result = await runAcceptAll(ids, (id) => reviewSuggestion(id, { accept: true }), {
    onStart: (all) => all.forEach((id) => delete rowError[id]),
  })
  for (const f of result.failed) rowError[f.id] = errorText(f.error)
  if (result.stoppedAfter !== null) {
    notice.value = `Stopped after ${result.stoppedAfter} of ${ids.length}: ${errorText(result.failed[result.failed.length - 1].error)}`
  } else {
    notice.value = result.failed.length
      ? `Accepted ${result.done.length}, ${result.failed.length} failed`
      : `Accepted ${result.done.length}`
  }
  busy.value = false
  await load()
}

onMounted(async () => {
  try {
    health.value = await fetchHealth()
  } catch (err) {
    const note = serviceNote(err)
    if (note) {
      serviceBanner.value = note
      return
    }
    loadError.value = errorText(err)
  }
  await load()
})
</script>

<style scoped>
.jev-container { min-height: 100%; max-width: 100vw; overflow-x: hidden; }
.page-header { padding: 16px 24px; background: #fff; border-bottom: 1px solid #dcdce2; }
.page-header h1 { margin: 4px 0 0; font-size: 20px; }
.back-link { font-size: 13px; color: #4a5bd4; text-decoration: none; }
.page-content { padding: 16px 24px; min-width: 0; }
.banner { padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
.banner-info { background: #fff6dc; border: 1px solid #e8d48a; }
.banner-error { background: #fde8e8; border: 1px solid #e3a3a3; }
.tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; max-width: 100%; }
.tab { flex: 0 1 auto; max-width: 100%; padding: 6px 12px; border: 1px solid #c9c9d1; background: #fff; border-radius: 6px; cursor: pointer; }
.tab.active { background: #4a5bd4; color: #fff; border-color: #4a5bd4; }
.tab.disabled { color: #8a8a94; background: #ececf0; cursor: not-allowed; }
.tab-note { font-size: 11px; }
.not-available { color: #6a6a74; }
.counts { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-bottom: 10px; font-size: 14px; align-items: center; }
.count-note { color: #a05a00; font-size: 12px; }
.filter-bar, .accept-all { display: flex; gap: 10px 14px; flex-wrap: wrap; align-items: end; margin-bottom: 10px; }
.field-hint { color: #b03030; font-size: 12px; margin: 0 0 10px; }
.filter-field { display: flex; flex-direction: column; font-size: 12px; gap: 2px; min-width: 0; }
.filter-field input { width: 110px; max-width: 100%; }
.filter-count, .notice { font-size: 13px; color: #55555e; }
.btn { padding: 5px 12px; border: 1px solid #4a5bd4; background: #4a5bd4; color: #fff; border-radius: 6px; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.rows { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px 16px; min-width: 0; background: #fff; border: 1px solid #dcdce2; border-left: 4px solid #c9a227; border-radius: 6px; padding: 10px 14px; }
.row.status-accepted { border-left-color: #2e9e5b; }
.row.status-changed { border-left-color: #4a5bd4; }
.row-main { flex: 1 1 260px; min-width: 0; overflow-wrap: anywhere; }
.row-title { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
.qtype { font-size: 12px; color: #6a6a74; }
.status-badge { font-size: 11px; text-transform: uppercase; color: #55555e; }
.texture { font-size: 13px; margin-top: 2px; }
.question summary { font-size: 12px; color: #4a5bd4; cursor: pointer; }
.question p { font-size: 12px; max-width: 70ch; margin: 4px 0; }
.answer { margin-top: 4px; font-size: 14px; }
.confidence { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.bar { width: 160px; max-width: 60%; height: 8px; background: #e6e6ec; border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: #4a5bd4; }
.bar-label { font-size: 12px; color: #55555e; }
.alternatives { font-size: 12px; color: #55555e; margin-top: 4px; }
.alt { margin-right: 10px; }
.row-error { color: #b03030; font-size: 12px; margin-top: 4px; }
.row-actions { display: flex; flex-direction: column; gap: 6px; align-items: stretch; min-width: 130px; }
.loading-state, .empty { color: #6a6a74; }

@media (max-width: 600px) {
  .page-header, .page-content { padding-left: 12px; padding-right: 12px; }
  .row-actions { flex: 1 1 100%; flex-direction: row; flex-wrap: wrap; min-width: 0; }
  .row-actions > * { flex: 1 1 auto; min-width: 0; }
}
</style>
