import { describe, it, expect, beforeEach } from 'vitest'
import { useLayers, HOTKEYS } from './useLayers'

describe('useLayers', () => {
  it('initializes with expected default values', () => {
    const { layers } = useLayers()
    expect(layers.grid).toBe(true)
    expect(layers.outline).toBe(true)
    expect(layers.tri).toBe(false)
    expect(layers.creases).toBe(false)
    expect(layers.hidden).toBe(false)
    expect(layers.onesided).toBe(false)
    expect(layers.xray).toBe(false)
    expect(layers.sync).toBe(true)
  })

  it('toggles layer state when toggleLayer is called', () => {
    const { layers, toggleLayer } = useLayers()
    expect(layers.tri).toBe(false)
    toggleLayer('tri')
    expect(layers.tri).toBe(true)
    toggleLayer('tri')
    expect(layers.tri).toBe(false)

    toggleLayer('onesided')
    expect(layers.onesided).toBe(true)
  })

  it('updates layer state via hotkey handler', () => {
    const { layers, handleKeyDown } = useLayers()

    // Test 'g' for grid
    expect(layers.grid).toBe(true)
    handleKeyDown({ key: 'g' } as KeyboardEvent)
    expect(layers.grid).toBe(false)

    // Test 't' for tri wireframe
    expect(layers.tri).toBe(false)
    handleKeyDown({ key: 't' } as KeyboardEvent)
    expect(layers.tri).toBe(true)

    // Test 'm' for onesided diagnostic
    expect(layers.onesided).toBe(false)
    handleKeyDown({ key: 'm' } as KeyboardEvent)
    expect(layers.onesided).toBe(true)

    // Test 'c' for soft creases
    expect(layers.creases).toBe(false)
    handleKeyDown({ key: 'c' } as KeyboardEvent)
    expect(layers.creases).toBe(true)

    // Test 'h' for hidden faces
    expect(layers.hidden).toBe(false)
    handleKeyDown({ key: 'h' } as KeyboardEvent)
    expect(layers.hidden).toBe(true)
  })

  it('ignores hotkeys if ctrl/alt/meta are pressed', () => {
    const { layers, handleKeyDown } = useLayers()
    expect(layers.tri).toBe(false)
    handleKeyDown({ key: 't', ctrlKey: true } as KeyboardEvent)
    expect(layers.tri).toBe(false)
    handleKeyDown({ key: 't', altKey: true } as KeyboardEvent)
    expect(layers.tri).toBe(false)
    handleKeyDown({ key: 't', metaKey: true } as KeyboardEvent)
    expect(layers.tri).toBe(false)
  })

  it('ignores hotkeys when typing into an input element', () => {
    const { layers, handleKeyDown } = useLayers()
    const target = { tagName: 'INPUT', type: 'text' } as unknown as HTMLElement
    handleKeyDown({ key: 'g', target } as unknown as KeyboardEvent)
    expect(layers.grid).toBe(true) // unchanged
  })

  it('does not block hotkeys when focused on a checkbox input (m8)', () => {
    const { layers, handleKeyDown } = useLayers()
    const target = { tagName: 'INPUT', type: 'checkbox' } as unknown as HTMLElement
    handleKeyDown({ key: 'g', target } as unknown as KeyboardEvent)
    expect(layers.grid).toBe(false)
  })
})
