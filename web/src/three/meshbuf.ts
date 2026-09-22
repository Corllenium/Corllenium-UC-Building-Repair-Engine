export interface MeshbufHeader {
  version: number
  name: string
  units: string
  unit_scale_m: number
  origin_offset: [number, number, number]
  bbox: { min: [number, number, number]; max: [number, number, number] }
  materials: Array<{ name: string; texture: string | null }>
  counts: { faces: number; edges: number }
  blocks: Array<{
    name: string
    dtype: 'f32' | 'u16' | 'u32' | 'i32' | 'u8'
    shape: number[]
    offset: number
    nbytes: number
  }>
}

export interface DecodedMeshbuf {
  header: MeshbufHeader
  positions: Float32Array
  uvs: Float32Array
  normals: Float32Array
  triMaterial: Uint16Array
  triFaceId: Uint32Array
  triRegion: Int32Array
  edgePositions: Float32Array
  edgeClass: Uint8Array
}

export function decodeMeshbuf(buffer: ArrayBuffer): DecodedMeshbuf {
  const bytes = new Uint8Array(buffer)
  const magic = String.fromCharCode(...bytes.slice(0, 4))
  if (magic !== 'UCMB') {
    throw new Error(`Invalid meshbuf magic: ${magic}`)
  }

  const view = new DataView(buffer)
  const version = view.getUint32(4, true)
  const hlen = view.getUint32(8, true)

  const headerStr = new TextDecoder().decode(bytes.slice(12, 12 + hlen))
  const header: MeshbufHeader = JSON.parse(headerStr.trim())
  const start = 12 + hlen

  const getArray = (name: string, ctor: any) => {
    const block = header.blocks.find(b => b.name === name)
    if (!block) return new ctor(0)
    const count = block.shape.reduce((a, b) => a * b, 1)
    return new ctor(buffer, start + block.offset, count)
  }

  return {
    header,
    positions: getArray('positions', Float32Array),
    uvs: getArray('uvs', Float32Array),
    normals: getArray('normals', Float32Array),
    triMaterial: getArray('tri_material', Uint16Array),
    triFaceId: getArray('tri_face_id', Uint32Array),
    triRegion: getArray('tri_region', Int32Array),
    edgePositions: getArray('edge_positions', Float32Array),
    edgeClass: getArray('edge_class', Uint8Array),
  }
}
