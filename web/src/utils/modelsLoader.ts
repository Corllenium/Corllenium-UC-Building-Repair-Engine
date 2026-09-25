import { formatErrorMessage } from './formatError'
import type { Model, SourceFile } from '../api/client'

export interface ModelsDataResult {
  models: Model[]
  sourceFiles: SourceFile[]
  errorMessage: string | null
}

export async function loadModelsData(
  fetchSrc: () => Promise<SourceFile[]>,
  fetchMods: () => Promise<Model[]>
): Promise<ModelsDataResult> {
  let models: Model[] = []
  let sourceFiles: SourceFile[] = []
  let errorMessage: string | null = null

  const [srcRes, modsRes] = await Promise.allSettled([fetchSrc(), fetchMods()])
  if (modsRes.status === 'fulfilled') {
    models = modsRes.value
  }
  if (srcRes.status === 'fulfilled') {
    sourceFiles = srcRes.value
  } else {
    errorMessage = formatErrorMessage(srcRes.reason)
  }
  if (modsRes.status === 'rejected' && srcRes.status === 'fulfilled') {
    errorMessage = formatErrorMessage(modsRes.reason)
  }

  return { models, sourceFiles, errorMessage }
}
