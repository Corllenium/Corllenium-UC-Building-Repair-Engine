export interface MaterialGroups {
  order: Uint32Array
  groups: { start: number; count: number; material: number }[]
}

/** Faces sorted by material so each material draws as one group; order[k] is the face drawn at slot k. */
export function groupByMaterial(triMaterial: ArrayLike<number>): MaterialGroups {
  const n = triMaterial.length
  const order = new Uint32Array(n)
  for (let i = 0; i < n; i++) order[i] = i
  order.sort((a, b) => triMaterial[a] - triMaterial[b] || a - b)
  const groups: MaterialGroups['groups'] = []
  let start = 0
  for (let k = 1; k <= n; k++) {
    if (k === n || triMaterial[order[k]] !== triMaterial[order[start]]) {
      groups.push({ start: start * 3, count: (k - start) * 3, material: triMaterial[order[start]] })
      start = k
    }
  }
  return { order, groups }
}

/** The API serves a version's textures by their FILE name, e.g. `…/textures/minecraft_quartz_block_side_-1.png`. */
export function textureUrl(versionId: number, texture: string | null): string | null {
  if (!texture) return null
  const name = texture.split('/').pop()!
  return `/api/versions/${versionId}/textures/${encodeURIComponent(name)}`
}
