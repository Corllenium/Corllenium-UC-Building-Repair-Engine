<template>
  <div class="models-container">
    <header class="page-header">
      <div class="brand">
        <h1>UC Model Fixer</h1>
        <span class="badge">Campus SketchUp &rarr; Unity 6 URP</span>
      </div>
      <div class="header-actions">
        <button class="btn btn-primary" @click="doRescan" :disabled="rescanning || loading">
          {{ rescanning ? 'Rescanning...' : 'Rescan Source Folder' }}
        </button>
        <button class="btn btn-secondary" @click="loadData" :disabled="loading || rescanning">Refresh</button>
      </div>
    </header>

    <main class="page-content">
      <div v-if="errorMessage" class="banner banner-warning" style="margin-bottom: 16px; padding: 12px 16px; background: #fff3cd; color: #856404; border: 1px solid #ffeeba; border-radius: 4px;">
        {{ errorMessage }}
      </div>

      <!-- Section: Available Source Files -->
      <section class="card">
        <h2>Available Campus Exports</h2>
        <p class="subtitle">Discovered in SketchUp export directory (<code>CHECKPOINT-17/split</code>)</p>

        <div v-if="loading && !sourceFiles.length" class="loading-state">Scanning source folder...</div>

        <table v-else class="data-table">
          <thead>
            <tr>
              <th>File Name</th>
              <th>Expected Triangles</th>
              <th>Status</th>
              <th style="text-align: right">Action</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in sourceFiles" :key="f.file">
              <td class="mono font-bold">{{ f.file }}</td>
              <td>{{ f.tri_count ? f.tri_count.toLocaleString() : '—' }}</td>
              <td>
                <span v-if="isImported(f.file)" class="tag tag-success">Imported</span>
                <span v-else class="tag tag-neutral">Not Imported</span>
              </td>
              <td style="text-align: right">
                <button
                  v-if="!isImported(f.file)"
                  class="btn btn-primary btn-sm"
                  :disabled="importing === f.file"
                  @click="doImport(f.file)"
                >
                  {{ importing === f.file ? 'Importing...' : 'Import' }}
                </button>
                <router-link
                  v-else
                  :to="`/workspace/${getModelBySource(f.file)!.id}`"
                  class="btn btn-secondary btn-sm"
                >
                  Open Workspace &rarr;
                </router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Section: Imported Models -->
      <section v-if="models.length" class="card">
        <h2>Imported Models</h2>
        <div class="grid-cards">
          <div v-for="m in models" :key="m.id" class="model-card">
            <div class="model-header">
              <h3 class="mono">{{ m.name }}</h3>
              <span class="version-count">{{ m.versions.length }} version(s)</span>
            </div>
            <div class="model-details">
              <div><strong>Source:</strong> {{ m.source_file }}</div>
              <div v-if="m.versions.length">
                <strong>Base Tris:</strong> {{ m.versions[0].tri_count.toLocaleString() }}
              </div>
              <div v-if="hasFixedVersion(m)" class="fixed-badge">
                Fixed: {{ getLatestVersion(m).tri_count.toLocaleString() }} tris
                ({{ getReduction(m) }}% fewer)
              </div>
            </div>
            <router-link :to="`/workspace/${m.id}`" class="btn btn-primary" style="margin-top: 12px">
              Open Inspection Workspace
            </router-link>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchSourceFiles, fetchModels, rescanModels, importModel, type SourceFile, type Model } from '../api/client'
import { formatErrorMessage } from '../utils/formatError'

const sourceFiles = ref<SourceFile[]>([])
const models = ref<Model[]>([])
const loading = ref(false)
const rescanning = ref(false)
const importing = ref<string | null>(null)
const errorMessage = ref<string | null>(null)

async function doRescan() {
  rescanning.value = true
  errorMessage.value = null
  try {
    const updated = await rescanModels()
    models.value = updated
    const src = await fetchSourceFiles()
    sourceFiles.value = src
  } catch (err: any) {
    errorMessage.value = formatErrorMessage(err)
  } finally {
    rescanning.value = false
  }
}

async function loadData() {
  loading.value = true
  errorMessage.value = null
  try {
    const [src, mods] = await Promise.all([fetchSourceFiles(), fetchModels()])
    sourceFiles.value = src
    models.value = mods
  } catch (err: any) {
    errorMessage.value = formatErrorMessage(err)
  } finally {
    loading.value = false
  }
}

function isImported(file: string): boolean {
  return models.value.some(m => m.source_file === file || m.source_file.endsWith(file))
}

function getModelBySource(file: string): Model | undefined {
  return models.value.find(m => m.source_file === file || m.source_file.endsWith(file))
}

function hasFixedVersion(m: Model): boolean {
  return m.versions.some(v => v.kind === 'fixed')
}

function getLatestVersion(m: Model) {
  return m.versions[m.versions.length - 1]
}

function getReduction(m: Model): string {
  const base = m.versions[0].tri_count
  const fixed = getLatestVersion(m).tri_count
  return (100 * (1 - fixed / base)).toFixed(1)
}

async function doImport(file: string) {
  importing.value = file
  errorMessage.value = null
  try {
    await importModel(file)
    await loadData()
  } catch (err: any) {
    errorMessage.value = formatErrorMessage(err)
  } finally {
    importing.value = null
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.models-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 16px;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #1c1d21;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #dcdde2;
  padding-bottom: 16px;
  margin-bottom: 24px;
}

.brand h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  color: #1f5bff;
  background: #eef3ff;
  padding: 2px 8px;
  border-radius: 4px;
  margin-top: 4px;
}

.card {
  background: #fff;
  border: 1px solid #dcdde2;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.card h2 {
  margin: 0 0 4px 0;
  font-size: 18px;
}

.subtitle {
  color: #676b75;
  font-size: 13px;
  margin-top: 0;
  margin-bottom: 16px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.data-table th, .data-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.data-table th {
  color: #676b75;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: #fcfcfd;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.btn {
  display: inline-block;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  text-decoration: none;
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

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}

.tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.tag-success {
  background: #e6f8ee;
  color: #0d8a43;
}

.tag-neutral {
  background: #f0f1f4;
  color: #676b75;
}

.grid-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.model-card {
  border: 1px solid #e2e4e9;
  border-radius: 6px;
  padding: 16px;
  background: #fafbfc;
  display: flex;
  flex-direction: column;
}

.model-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 10px;
}

.model-header h3 {
  margin: 0;
  font-size: 15px;
}

.version-count {
  font-size: 12px;
  color: #676b75;
}

.model-details {
  font-size: 13px;
  color: #444;
  line-height: 1.5;
  flex: 1;
}

.fixed-badge {
  margin-top: 6px;
  color: #0d8a43;
  font-weight: 600;
}
</style>
