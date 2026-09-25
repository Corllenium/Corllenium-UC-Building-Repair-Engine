import { describe, it, expect } from 'vitest'
import { formatFaceSourceInfo } from './faceInspection'
import type { FaceDetails } from '../api/client'

describe('formatFaceSourceInfo', () => {
  it('formats BEFORE view as "source line N"', () => {
    const details: FaceDetails = {
      face_id: 0,
      line: 42,
      vertices: [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
    }
    expect(formatFaceSourceInfo('before', details)).toBe('source line 42')
  })

  it('formats AFTER view with single source face as "source line N"', () => {
    const details: FaceDetails = {
      face_id: 5,
      line: 100,
      vertices: [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
      source_faces: [{ face_id: 12, line: 88 }],
    }
    expect(formatFaceSourceInfo('after', details)).toBe('source line 88')
  })

  it('formats AFTER view with multiple source faces as "merged from N original faces (lines ...)"', () => {
    const details: FaceDetails = {
      face_id: 5,
      line: 100,
      vertices: [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
      source_faces: [
        { face_id: 1, line: 10 },
        { face_id: 2, line: 12 },
        { face_id: 3, line: 15 },
      ],
    }
    expect(formatFaceSourceInfo('after', details)).toBe(
      'merged from 3 original faces (lines 10, 12, 15)'
    )
  })

  it('formats AFTER view fallback without source_faces as "source line N"', () => {
    const details: FaceDetails = {
      face_id: 0,
      line: 77,
      vertices: [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
    }
    expect(formatFaceSourceInfo('after', details)).toBe('source line 77')
  })

  it('formats AFTER view with invented face (face_id -1)', () => {
    const details: FaceDetails = {
      face_id: 10,
      line: -1,
      vertices: [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
      source_faces: [{ face_id: -1, line: -1 }],
    }
    expect(formatFaceSourceInfo('after', details)).toBe('invented face (solidify)')
  })
})

