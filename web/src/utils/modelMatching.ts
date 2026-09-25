import type { Model } from '../api/client'

export function isSourceImported(models: Model[], file: string): boolean {
  return models.some(m => m.source_file === file)
}

export function findModelBySource(models: Model[], file: string): Model | undefined {
  return models.find(m => m.source_file === file)
}
