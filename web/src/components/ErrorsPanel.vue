<template>
  <section class="errors-panel">
    <header>
      <strong>Errors</strong>
      <button v-if="!before" class="btn" :disabled="busyBefore" @click="$emit('find', 'before')">
        {{ busyBefore ? 'Finding errors in BEFORE…' : 'Find errors (BEFORE)' }}
      </button>
      <button v-if="hasAfter && !after" class="btn" :disabled="busyAfter" @click="$emit('find', 'after')">
        {{ busyAfter ? 'Finding errors in AFTER…' : 'Find errors (AFTER)' }}
      </button>
    </header>
    <table v-if="before || after" class="legend">
      <thead><tr><th></th><th>Kind</th><th>BEFORE</th><th>AFTER</th></tr></thead>
      <tbody>
        <tr v-for="k in ERROR_KINDS" :key="k.kind">
          <td><input type="checkbox" v-model="filter.enabled[k.kind]" /></td>
          <td>
            <span class="swatch" :style="{ background: hex(k.color) }"></span>{{ k.label }}
            <button
              v-if="catalogueId(k.kind)"
              type="button"
              class="info-btn"
              aria-label="What is this error?"
              :title="infoTitle(k.kind)"
              @click.stop.prevent="$emit('info', catalogueId(k.kind)!)"
            >i</button>
          </td>
          <td>{{ before ? countOf(before, k.kind).toLocaleString() : '—' }}</td>
          <td>{{ after ? countOf(after, k.kind).toLocaleString() : '—' }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="before || after" class="modes">
      <label><input type="checkbox" v-model="filter.isolate" /> Isolate errors</label>
      <label><input type="checkbox" v-model="filter.blink" /> Blink flicker</label>
    </div>
    <div v-if="before" class="spots">
      <strong>Worst spots (BEFORE)</strong>
      <select v-model="spotKind">
        <option v-for="k in ERROR_KINDS" :key="k.kind" :value="k.kind">{{ k.label }}</option>
      </select>
      <ol>
        <li v-for="(s, n) in before.spots[spotKind]" :key="n">
          {{ s.label }} <button class="btn-link" @click="$emit('fly', s, 'before')">fly to</button>
        </li>
      </ol>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ERROR_KINDS, countOf, type ErrorFilter, type ErrorKind, type ErrorsFile, type ErrorSpot } from '../utils/errorLayers'
import { ERROR_KIND_CATALOGUE, type Catalogue } from '../utils/errorsDoc'

const props = defineProps<{ before: ErrorsFile | null; after: ErrorsFile | null; busyBefore: boolean; busyAfter: boolean;
  filter: ErrorFilter; hasAfter: boolean; catalogue: Catalogue | null }>()
defineEmits<{ (e: 'find', panel: 'before' | 'after'): void; (e: 'fly', spot: ErrorSpot, panel: 'before' | 'after'): void;
  (e: 'info', kindId: string): void }>()

const spotKind = ref<ErrorKind>('flicker_diff')
const hex = (c: number) => '#' + c.toString(16).padStart(6, '0')
const catalogueId = (kind: ErrorKind): string | null => ERROR_KIND_CATALOGUE[kind] ?? null
// Same wording as the layer (i) buttons: specific once the catalogue has loaded, generic before.
function infoTitle(kind: ErrorKind): string {
  const id = catalogueId(kind)
  const found = id ? props.catalogue?.kinds.find(kk => kk.id === id) : undefined
  return found ? `About: ${found.title}` : 'About this error'
}
</script>

<style scoped>
.errors-panel { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 10px 12px; font-size: 13px; }
.errors-panel header { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.legend { border-collapse: collapse; width: 100%; }
.legend td, .legend th { padding: 2px 6px; text-align: left; }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
.modes { display: flex; gap: 16px; margin: 8px 0; }
.spots ol { margin: 6px 0 0 18px; padding: 0; max-height: 180px; overflow: auto; }
.btn-link { background: none; border: none; color: #1f5bff; cursor: pointer; padding: 0 4px; }
.info-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 1px solid #b8bcc4;
  background: #fff;
  color: #57606a;
  font-size: 10px;
  font-style: italic;
  font-weight: 700;
  line-height: 1;
  padding: 0;
  cursor: pointer;
  flex-shrink: 0;
  margin-left: 4px;
}
.info-btn:hover {
  background: #eaecef;
  color: #1c1d21;
}
</style>
