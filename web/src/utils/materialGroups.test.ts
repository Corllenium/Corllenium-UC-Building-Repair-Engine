import { describe, it, expect } from 'vitest'
import { groupByMaterial, textureUrl } from './materialGroups'

describe('groupByMaterial', () => {
  it('sorts faces by material into one group per material, keeping face order within a material', () => {
    const { order, groups } = groupByMaterial([2, 0, 2, 1, 0])
    expect(Array.from(order)).toEqual([1, 4, 3, 0, 2])
    expect(groups).toEqual([
      { start: 0, count: 6, material: 0 },
      { start: 6, count: 3, material: 1 },
      { start: 9, count: 6, material: 2 },
    ])
  })

  it('handles an empty model', () => {
    const { order, groups } = groupByMaterial([])
    expect(order.length).toBe(0)
    expect(groups).toEqual([])
  })
})

describe('textureUrl', () => {
  it('asks the API for a texture by its file name', () => {
    expect(textureUrl(6, 'tex/minecraft_quartz_block_side_-1.png'))
      .toBe('/api/versions/6/textures/minecraft_quartz_block_side_-1.png')
    expect(textureUrl(6, null)).toBeNull()
  })
})
