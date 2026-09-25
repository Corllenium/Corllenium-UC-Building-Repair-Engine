import type { FaceDetails } from '../api/client'

export function formatFaceSourceInfo(viewKind: 'before' | 'after', details: FaceDetails): string {
  if (viewKind === 'before') {
    return details.line > 0 ? `source line ${details.line}` : 'no source line'
  }
  // after view
  if (details.source_faces && details.source_faces.length > 1) {
    const lines = details.source_faces.map(sf => (sf.line > 0 ? String(sf.line) : 'invented')).join(', ')
    return `merged from ${details.source_faces.length} original faces (lines ${lines})`
  }
  if (details.source_faces && details.source_faces.length === 1) {
    const sf = details.source_faces[0]
    if (sf.face_id === -1 || sf.line <= 0) {
      return 'invented face (solidify)'
    }
    return `source line ${sf.line}`
  }
  return 'no provenance recorded for this version'
}
