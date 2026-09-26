import { describe, it, expect, vi } from 'vitest'
import * as THREE from 'three'
import { texturedSurfaceMaterials, disposeObjects } from './Viewport'

/** A stand-in for TextureLoader.load: a fresh Texture per call, each call's onError kept to fire
 *  later -- as the real loader's does, from the image's error event. */
function fakeLoader() {
  const calls: { url: string; texture: THREE.Texture; onError: () => void }[] = []
  const load = (url: string, onError: () => void) => {
    const texture = new THREE.Texture()
    calls.push({ url, texture, onError })
    return texture
  }
  return { load, calls }
}

const MATERIALS = [
  { name: 'stone', texture: 'tex/stone.png' },
  { name: 'plain', texture: null },
  { name: 'stone_again', texture: 'tex/stone.png' },   // a second material on the same file
  { name: 'brick', texture: 'tex/brick.png' },
]
const grey = (i: number) => new THREE.Color().setScalar(0.8 + (i % 5) * 0.04).getHex()

describe('the textured surface (review M8)', () => {
  it('loads each texture file once and shares it between the materials that use it', () => {
    const { load, calls } = fakeLoader()
    const { materials, textures } = texturedSurfaceMaterials(MATERIALS, 6, load)
    expect(calls.map(c => c.url)).toEqual(['/api/versions/6/textures/stone.png', '/api/versions/6/textures/brick.png'])
    expect(materials[0].map).toBe(calls[0].texture)
    expect(materials[2].map).toBe(calls[0].texture)
    expect([...textures.values()]).toEqual([calls[0].texture, calls[1].texture])
  })

  it('draws a texture that fails to load in the flat grey, not black, on every material using it', () => {
    const { load, calls } = fakeLoader()
    const { materials } = texturedSurfaceMaterials(MATERIALS, 6, load)
    const versions = materials.map(m => m.version)
    calls[0].onError()                                   // stone.png is missing
    for (const k of [0, 2]) {
      expect(materials[k].map).toBeNull()
      expect(materials[k].color.getHex()).toBe(grey(k))
      expect(materials[k].version).toBeGreaterThan(versions[k])     // needsUpdate was set
    }
    expect(materials[1].color.getHex()).toBe(grey(1))    // the untextured path's own grey
    expect(materials[3].map).toBe(calls[1].texture)      // brick is untouched
  })

  it('gives the no-material fallback the same options as every other material', () => {
    const { load } = fakeLoader()
    const { materials } = texturedSurfaceMaterials(MATERIALS, 6, load)
    expect(materials).toHaveLength(MATERIALS.length + 1)
    for (const m of materials) {
      expect([m.side, m.roughness, m.metalness, m.polygonOffset, m.polygonOffsetFactor, m.polygonOffsetUnits])
        .toEqual([THREE.DoubleSide, 0.9, 0.0, true, 1, 1])
    }
    expect(materials[MATERIALS.length].map).toBeNull()
    expect(materials[MATERIALS.length].color.getHex()).toBe(0xcccccc)
  })

  it('disposes a texture shared by several materials exactly once', () => {
    const { load, calls } = fakeLoader()
    const { materials, textures } = texturedSurfaceMaterials(MATERIALS, 6, load)
    const spies = calls.map(c => vi.spyOn(c.texture, 'dispose'))
    const mesh = new THREE.Mesh(new THREE.BufferGeometry(), materials)
    disposeObjects([mesh], textures.values())
    expect(spies.map(s => s.mock.calls.length)).toEqual([1, 1])
  })
})
