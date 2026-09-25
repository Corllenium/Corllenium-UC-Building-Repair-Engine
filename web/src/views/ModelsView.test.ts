import { describe, it, expect, vi } from 'vitest'
import { ApiError } from '../api/client'
import { formatErrorMessage } from '../utils/formatError'

describe('ModelsView error formatting & ApiError', () => {
  it('exposes status and retryAfter on ApiError', () => {
    const err = new ApiError('Locked', 409, 10)
    expect(err.status).toBe(409)
    expect(err.retryAfter).toBe(10)
    expect(err.message).toBe('Locked')
  })

  it('formats 409 status as export rebuilding message with retryAfter seconds', () => {
    const errWith10 = new ApiError('Locked', 409, 10)
    expect(formatErrorMessage(errWith10)).toBe('Export folder is being rebuilt, try again in 10 s')

    const errWithDefault = new ApiError('Locked', 409)
    expect(formatErrorMessage(errWithDefault)).toBe('Export folder is being rebuilt, try again in 5 s')
  })

  it('formats regular errors with their message', () => {
    const err404 = new ApiError('Model not found', 404)
    expect(formatErrorMessage(err404)).toBe('Model not found')

    const err422 = new ApiError('Manifest mismatch', 422)
    expect(formatErrorMessage(err422)).toBe('Manifest mismatch')
  })

  it('matches file names exactly, not endsWith', async () => {
    const { isSourceImported, findModelBySource } = await import('../utils/modelMatching')
    const models = [
      { id: 1, name: 'other_cube', source_file: 'other_cube.obj', created_at: '', versions: [] },
      { id: 2, name: 'prefix_cube', source_file: 'prefix_cube.obj', created_at: '', versions: [] },
    ]

    // "cube.obj" is a suffix of "other_cube.obj" and "prefix_cube.obj", but should NOT match
    expect(isSourceImported(models, 'cube.obj')).toBe(false)
    expect(findModelBySource(models, 'cube.obj')).toBeUndefined()

    // Exact matches succeed
    expect(isSourceImported(models, 'other_cube.obj')).toBe(true)
    expect(findModelBySource(models, 'other_cube.obj')?.id).toBe(1)
  })

  it('allows loading models when source scanning returns 409 (m6 UX gap)', async () => {
    const { loadModelsData } = await import('../utils/modelsLoader')
    const fetchSourceFiles = vi.fn().mockRejectedValue(new ApiError('Source locked', 409, 5))
    const fetchModels = vi.fn().mockResolvedValue([
      { id: 1, name: 'existing_model', source_file: 'existing.obj', created_at: '', versions: [] },
    ])

    const res = await loadModelsData(fetchSourceFiles, fetchModels)
    expect(res.models).toHaveLength(1)
    expect(res.models[0].name).toBe('existing_model')
    expect(res.sourceFiles).toHaveLength(0)
    expect(res.errorMessage).toBe('Export folder is being rebuilt, try again in 5 s')
  })
})
