import { describe, it, expect } from 'vitest'
import * as THREE from 'three'
import { DEPTH_BIAS_GLSL } from './Viewport'

// CHTM 5th floor: the bounding-box diagonal loadModel fits the camera to (review I2).
const SIZE = 2237
const OVERVIEW = SIZE * 1.45        // loadModel's camera distance
const FLY_TO_MIN = 96               // flyTo's closest: max(size, 60) * 1.6
const DEPTH_STEP = 2 ** -24         // one step of a 24-bit depth buffer, in window depth [0, 1]

/** A camera set up exactly as Viewport's (fov 42, loadModel's near and far), `distance` from the
 *  origin and looking at it. */
function camera(distance: number): THREE.PerspectiveCamera {
  const cam = new THREE.PerspectiveCamera(42, 1.6, Math.max(0.01, SIZE / 2000), SIZE * 20)
  cam.up.set(0, 0, 1)
  cam.position.copy(new THREE.Vector3(-0.45, -0.55, 0.7).normalize().multiplyScalar(distance))
  cam.lookAt(0, 0, 0)
  cam.updateMatrixWorld()
  cam.updateProjectionMatrix()
  return cam
}

/** Where the vertex shader's depth-bias line puts a world point, emulated on the CPU: the NDC
 *  position (x, y: the pixel; z: the depth) of the point drawn with DEPTH_BIAS_GLSL. */
function drawnWithBias(glsl: string, cam: THREE.PerspectiveCamera, p: THREE.Vector3): THREE.Vector3 {
  const mv = new THREE.Vector4(p.x, p.y, p.z, 1).applyMatrix4(cam.matrixWorldInverse)
  const pull = glsl.match(/gl_Position = projectionMatrix \* vec4\(mvPosition\.xyz \* ([0-9.]+), 1\.0\);/)
  const nudge = glsl.match(/gl_Position\.z -= ([0-9.]+) \* gl_Position\.w;/)
  let clip: THREE.Vector4
  if (pull) {
    const k = Number(pull[1])
    clip = new THREE.Vector4(mv.x * k, mv.y * k, mv.z * k, 1).applyMatrix4(cam.projectionMatrix)
  } else if (nudge) {
    clip = mv.clone().applyMatrix4(cam.projectionMatrix)
    clip.z -= Number(nudge[1]) * clip.w
  } else {
    throw new Error(`unrecognised depth bias: ${glsl}`)
  }
  return new THREE.Vector3(clip.x / clip.w, clip.y / clip.w, clip.z / clip.w)
}

/** The same point drawn plainly, as the wall or surface it sits on is. */
function drawnPlain(cam: THREE.PerspectiveCamera, p: THREE.Vector3): THREE.Vector3 {
  return p.clone().project(cam)
}

/** A point `behind` inches beyond the look-at point, on the camera's own line of sight. */
function onSightLine(cam: THREE.PerspectiveCamera, fromTarget: number): THREE.Vector3 {
  const dir = new THREE.Vector3(0, 0, 0).sub(cam.position).normalize()
  return dir.multiplyScalar(fromTarget)
}

describe('the crack-dot and open-edge depth bias (review I2)', () => {
  it('keeps the pixel and only moves the depth toward the eye', () => {
    const cam = camera(OVERVIEW)
    const p = new THREE.Vector3(310, -420, 55)
    const biased = drawnWithBias(DEPTH_BIAS_GLSL, cam, p), plain = drawnPlain(cam, p)
    expect(biased.x).toBeCloseTo(plain.x, 9)
    expect(biased.y).toBeCloseTo(plain.y, 9)
    expect(biased.z).toBeLessThan(plain.z)
  })

  it('still wins the depth test on its own surface, at the overview and close up', () => {
    for (const distance of [OVERVIEW, FLY_TO_MIN]) {
      const cam = camera(distance)
      const p = new THREE.Vector3(0, 0, 0)
      const lead = (drawnPlain(cam, p).z - drawnWithBias(DEPTH_BIAS_GLSL, cam, p).z) / 2   // in window depth
      expect(lead).toBeGreaterThan(4 * DEPTH_STEP)
    }
  })

  it('is hidden by a real wall one foot in front of it at the overview (the NDC nudge showed it through 114 ft)', () => {
    const cam = camera(OVERVIEW)
    const dot = onSightLine(cam, 0)
    const wall = onSightLine(cam, -12)   // 12 in nearer the eye, on the same pixel
    expect(drawnWithBias(DEPTH_BIAS_GLSL, cam, dot).z).toBeGreaterThan(drawnPlain(cam, wall).z)
  })

  it('is hidden by a wall an inch in front of it at the 96 in fly-to distance', () => {
    const cam = camera(FLY_TO_MIN)
    const dot = onSightLine(cam, 0)
    const wall = onSightLine(cam, -1)
    expect(drawnWithBias(DEPTH_BIAS_GLSL, cam, dot).z).toBeGreaterThan(drawnPlain(cam, wall).z)
  })
})
