import { describe, it, expect } from 'vitest'
import {
  ERROR_KINDS, FACE_KINDS, defaultFilter, overlayFaces, blinkColors, partnersOf, kindsOf,
  openEdgeSegments, crackPoints, toViewer, materialColor, countOf, type ErrorsFile, partnerIndex,
  chooseFace,
} from './errorLayers'

const file: ErrorsFile = {
  version: 1, n_faces: 6,
  counts: { flicker_diff: 2, flicker_same: 0, reversed: 1, hidden: 2, loose: 0, open_edges: 1, cracks: 1 },
  faces: { flicker_diff: [0, 1], flicker_same: [], reversed: [1], hidden: [4, 5], loose: [] },
  layers: { facade: [0, 3] }, layer_counts: { facade: 2 },
  open_edges: [[10, 0, 0, 20, 0, 0]], cracks: [[15, 5, 0]],
  flicker_pairs: [[0, 1, 100, true]],
  spots: { flicker_diff: [], flicker_same: [], reversed: [], hidden: [], loose: [], open_edges: [], cracks: [], facade: [] },
}

describe('errorLayers', () => {
  it('lists the seven error kinds and the facade layer in priority order with the spec colours', () => {
    expect(ERROR_KINDS.map(k => k.kind)).toEqual(
      ['flicker_diff', 'flicker_same', 'reversed', 'hidden', 'loose', 'open_edges', 'cracks', 'facade'])
    expect(ERROR_KINDS[0].color).toBe(0xd8282f)
    expect(FACE_KINDS).toEqual(['flicker_diff', 'flicker_same', 'reversed', 'hidden', 'loose', 'facade'])
  })

  it('defaults to just the flicker kinds -- the owner s "especially flickering" focus', () => {
    const f = defaultFilter()
    expect(f.enabled).toEqual({
      flicker_diff: true, flicker_same: true, reversed: false, hidden: false, loose: false,
      open_edges: false, cracks: false, facade: false,
    })
    expect(f.isolate).toBe(false)
    expect(f.blink).toBe(false)
  })

  it('draws the facade in teal only when asked, and never over an error colour', () => {
    const f = defaultFilter()
    expect(f.enabled.facade).toBe(false)
    f.enabled.facade = true
    const { faces, colors } = overlayFaces(file, f)
    // hidden is off by default, so faces 4 and 5 (hidden only) are not drawn
    expect(faces).toEqual([0, 1, 3])
    // face 0 is flicker_diff AND facade: red wins; face 3 (slot 2) is facade only: teal
    expect(Array.from(colors.slice(0, 3)).map(v => Math.round(v * 255))).toEqual([0xd8, 0x28, 0x2f])
    expect(Array.from(colors.slice(18, 21)).map(v => Math.round(v * 255))).toEqual([0x0d, 0x94, 0x88])
  })

  it('counts errors from counts and the facade from layer_counts', () => {
    expect(countOf(file, 'reversed')).toBe(1)
    expect(countOf(file, 'facade')).toBe(2)
  })

  it('draws only the enabled kinds, a face in two kinds in the first one', () => {
    const f = defaultFilter()
    f.enabled.reversed = true
    f.enabled.hidden = true
    const { faces, colors } = overlayFaces(file, f)
    expect(faces).toEqual([0, 1, 4, 5])
    // face 1 is flicker_diff AND reversed: red wins
    expect(Array.from(colors.slice(9, 12)).map(v => Math.round(v * 255))).toEqual([0xd8, 0x28, 0x2f])
    f.enabled.flicker_diff = false
    expect(overlayFaces(file, f).faces).toEqual([1, 4, 5])
    expect(Array.from(overlayFaces(file, f).colors.slice(0, 3)).map(v => Math.round(v * 255))).toEqual([0x96, 0x50, 0xff])
  })

  it('blinks a flicker face between its own material and its partner s', () => {
    const tm = [3, 7, 0, 0, 0, 0]
    const a = blinkColors(file, [0, 1], tm, 0)
    const b = blinkColors(file, [0, 1], tm, 1)
    expect(Array.from(a.slice(0, 3))).toEqual(Array.from(b.slice(9, 12)))  // face 0 now = face 1 then
    expect(Array.from(a.slice(0, 3))).not.toEqual(Array.from(b.slice(0, 3)))
  })

  it('names a face s partners and kinds', () => {
    expect(partnersOf(file, 1)).toEqual([{ face: 0, shared: 100, opposite: true }])
    expect(kindsOf(file, 1)).toEqual(['flicker_diff', 'reversed'])
    expect(kindsOf(file, 2)).toEqual([])
    expect(kindsOf(file, 3)).toEqual(['facade'])
  })

  it('moves lines and points into the viewer s frame', () => {
    const origin = [10, 0, 0]
    expect(Array.from(openEdgeSegments(file, origin))).toEqual([0, 0, 0, 10, 0, 0])
    expect(Array.from(crackPoints(file, origin))).toEqual([5, 5, 0])
    expect(toViewer([11, 2, 3], origin)).toEqual([1, 2, 3])
  })

  it('gives different materials different colours', () => {
    expect(materialColor(0)).not.toBe(materialColor(1))
    expect(materialColor(12)).toBe(materialColor(0))
  })

  it('blinks 40,000 faces with 20,000 pairs in under 1,000 ms via cached partner lookup', () => {
    const flicker_pairs: [number, number, number, boolean][] = []
    for (let k = 0; k < 20000; k++) {
      flicker_pairs.push([2*k, 2*k+1, 1, true])
    }
    const bigFile: ErrorsFile = {
      version: 1, n_faces: 40000,
      counts: { flicker_diff: 40000, flicker_same: 0, reversed: 0, hidden: 0, loose: 0, open_edges: 0, cracks: 0 },
      faces: { flicker_diff: Array.from({length: 40000}, (_, i) => i), flicker_same: [], reversed: [], hidden: [], loose: [] },
      layers: { facade: [] }, layer_counts: { facade: 0 },
      open_edges: [], cracks: [],
      flicker_pairs,
      spots: { flicker_diff: [], flicker_same: [], reversed: [], hidden: [], loose: [], open_edges: [], cracks: [], facade: [] },
    }
    const triMaterial = Array.from({length: 40000}, (_, i) => i % 12)
    const allFaces = Array.from({length: 40000}, (_, i) => i)

    const start = performance.now()
    const colors1 = blinkColors(bigFile, allFaces, triMaterial, 1)
    const elapsed = performance.now() - start

    expect(elapsed).toBeLessThan(1000)
    // face 0 phase=1 should equal face 1 phase=0 (they blink in sync)
    const colors0 = blinkColors(bigFile, allFaces, triMaterial, 0)
    expect(Array.from(colors1.slice(0, 3))).toEqual(Array.from(colors0.slice(9, 12)))
    // partnersOf on face 0 should find exactly one partner
    expect(partnerIndex(bigFile).get(0)).toHaveLength(1)
  })
})

describe('chooseFace (review I3)', () => {
  // the overlay draws faces 7, 9 and 42 in its slots 0, 1 and 2
  const overlayFaceIds = [7, 9, 42]

  it('in Isolate or X-ray, a click on the overlay picks the error face drawn there, not the ghost wall', () => {
    expect(chooseFace(true, { faceIndex: 2, point: 'on the error' }, overlayFaceIds,
      { faceIndex: 5, point: 'on the wall' }, null))
      .toEqual({ faceId: 42, point: 'on the error' })
  })

  it('with the surface opaque, picks the surface as before, through faceOrder on the textured mesh', () => {
    expect(chooseFace(false, { faceIndex: 2, point: 'on the error' }, overlayFaceIds,
      { faceIndex: 1, point: 'on the wall' }, [3, 8, 0]))
      .toEqual({ faceId: 8, point: 'on the wall' })
    expect(chooseFace(false, null, null, { faceIndex: 1, point: 'on the wall' }, null))
      .toEqual({ faceId: 1, point: 'on the wall' })
  })

  it('falls back to the surface when the click misses every overlay face', () => {
    expect(chooseFace(true, null, overlayFaceIds, { faceIndex: 5, point: 'on the wall' }, null))
      .toEqual({ faceId: 5, point: 'on the wall' })
    expect(chooseFace(true, null, overlayFaceIds, { faceIndex: 1, point: 'on the wall' }, [3, 8, 0]))
      .toEqual({ faceId: 8, point: 'on the wall' })
  })

  it('picks nothing when the click misses the model', () => {
    expect(chooseFace(true, null, overlayFaceIds, null, null)).toBeNull()
    expect(chooseFace(false, null, null, null, null)).toBeNull()
  })
})
