import { describe, it, expect } from 'vitest'
import * as THREE from 'three'
import { errorOverlayMaterial } from './Viewport'

describe('the error overlay (review I3)', () => {
  it('is met by a pick ray from its front and from its back', () => {
    // one triangle in z = 0, wound to face +z; interior flicker faces face away from half the views
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(new Float32Array([0, 0, 0, 10, 0, 0, 0, 10, 0]), 3))
    const overlay = new THREE.Mesh(geom, errorOverlayMaterial())
    const raycaster = new THREE.Raycaster()

    raycaster.set(new THREE.Vector3(2, 2, 50), new THREE.Vector3(0, 0, -1))    // from the front
    expect(raycaster.intersectObject(overlay)[0]?.faceIndex).toBe(0)
    raycaster.set(new THREE.Vector3(2, 2, -50), new THREE.Vector3(0, 0, 1))    // from behind
    expect(raycaster.intersectObject(overlay)[0]?.faceIndex).toBe(0)
  })

  it('keeps its look: vertex colours, both sides drawn, pulled in front of the surface it lies on', () => {
    const m = errorOverlayMaterial()
    expect(m.vertexColors).toBe(true)
    expect(m.side).toBe(THREE.DoubleSide)
    expect([m.polygonOffset, m.polygonOffsetFactor, m.polygonOffsetUnits]).toEqual([true, -1, -1])
  })
})
