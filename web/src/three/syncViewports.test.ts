import { describe, it, expect, vi } from 'vitest'
import * as THREE from 'three'
import { syncViewports, type Viewport } from './Viewport'

describe('syncViewports', () => {
  it('copies camera position, quaternion, controls target, zoom, and fov', () => {
    // Create mock viewports
    const cameraA = new THREE.PerspectiveCamera(45, 1, 0.1, 1000)
    cameraA.position.set(10, 20, 30)
    cameraA.quaternion.set(0.1, 0.2, 0.3, 0.9)
    cameraA.zoom = 2.5
    cameraA.fov = 60

    const controlsA = {
      target: new THREE.Vector3(1, 2, 3),
      listeners: {} as Record<string, Array<() => void>>,
      addEventListener(type: string, fn: () => void) {
        this.listeners[type] = this.listeners[type] || []
        this.listeners[type].push(fn)
      },
      removeEventListener(type: string, fn: () => void) {
        this.listeners[type] = (this.listeners[type] || []).filter(cb => cb !== fn)
      },
      update: vi.fn(),
    }

    const cameraB = new THREE.PerspectiveCamera(42, 1, 0.1, 1000)
    cameraB.position.set(0, 0, 0)
    cameraB.quaternion.set(0, 0, 0, 1)
    cameraB.zoom = 1.0
    cameraB.fov = 42

    const controlsB = {
      target: new THREE.Vector3(0, 0, 0),
      listeners: {} as Record<string, Array<() => void>>,
      addEventListener(type: string, fn: () => void) {
        this.listeners[type] = this.listeners[type] || []
        this.listeners[type].push(fn)
      },
      removeEventListener(type: string, fn: () => void) {
        this.listeners[type] = (this.listeners[type] || []).filter(cb => cb !== fn)
      },
      update: vi.fn(),
    }

    const vpA = { camera: cameraA, controls: controlsA } as unknown as Viewport
    const vpB = { camera: cameraB, controls: controlsB } as unknown as Viewport

    const dispose = syncViewports(vpA, vpB)

    // Trigger change on A
    controlsA.listeners['change']?.forEach(fn => fn())

    expect(cameraB.position.x).toBeCloseTo(10)
    expect(cameraB.position.y).toBeCloseTo(20)
    expect(cameraB.position.z).toBeCloseTo(30)
    expect(cameraB.quaternion.x).toBeCloseTo(0.1)
    expect(controlsB.target.x).toBeCloseTo(1)
    expect(controlsB.update).toHaveBeenCalled()

    // Assert zoom and fov are copied
    expect(cameraB.zoom).toBe(2.5)
    expect(cameraB.fov).toBe(60)

    dispose()
  })
})
