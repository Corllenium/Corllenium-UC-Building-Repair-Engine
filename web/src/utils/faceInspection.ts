import type { FaceDetails } from '../api/client'

export function formatFaceSourceInfo(viewKind: 'before' | 'after', details: FaceDetails): string {
  if (viewKind === 'before') {
    return `source line ${details.line}`
  }
  // after view
  if (details.source_faces && details.source_faces.length > 1) {
    const lines = details.source_faces.map(sf => sf.line).join(', ')
    return `merged from ${details.source_faces.length} original faces (lines ${lines})`
  }
  if (details.source_faces && details.source_faces.length === 1) {
    return `source line ${details.source_faces[0].line}`
  }
  return `source line ${details.line}`
}
