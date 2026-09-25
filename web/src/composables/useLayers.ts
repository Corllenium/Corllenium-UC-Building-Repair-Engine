import { reactive } from 'vue'

export interface LayerState {
  grid: boolean
  outline: boolean
  tri: boolean
  creases: boolean
  hidden: boolean
  onesided: boolean
  xray: boolean
  sync: boolean
}

export const HOTKEYS: Record<string, keyof LayerState> = {
  g: 'grid',
  o: 'outline',
  t: 'tri',
  c: 'creases',
  h: 'hidden',
  m: 'onesided',
  x: 'xray',
  s: 'sync',
}

export function useLayers(initial?: Partial<LayerState>) {
  const layers = reactive<LayerState>({
    grid: true,
    outline: true,
    tri: false,
    creases: false,
    hidden: false,
    onesided: false,
    xray: false,
    sync: true,
    ...initial,
  })

  function toggleLayer(layer: keyof LayerState) {
    layers[layer] = !layers[layer]
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.ctrlKey || e.altKey || e.metaKey) return
    const target = e.target as HTMLElement | null
    if (target) {
      const tag = target.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable) {
        return
      }
    }
    const key = e.key.toLowerCase()
    const layer = HOTKEYS[key]
    if (layer) {
      if (typeof e.preventDefault === 'function') {
        e.preventDefault()
      }
      toggleLayer(layer)
    }
  }

  return {
    layers,
    toggleLayer,
    handleKeyDown,
  }
}
