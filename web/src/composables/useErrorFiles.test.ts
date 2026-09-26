import { describe, it, expect, vi } from 'vitest'
import { nextTick, isProxy } from 'vue'
import { useErrorFiles } from './useErrorFiles'
import type { ErrorsFile } from '../utils/errorLayers'

function makeFile(): ErrorsFile {
  return {
    version: 2, n_faces: 6,
    counts: { flicker_diff: 2, flicker_same: 0, reversed: 1, hidden: 2, loose: 0, open_edges: 1, cracks: 1 },
    faces: { flicker_diff: [0, 1], flicker_same: [], reversed: [1], hidden: [4, 5], loose: [] },
    layers: { facade: [0, 3] }, layer_counts: { facade: 2 },
    open_edges: [[10, 0, 0, 20, 0, 0]], cracks: [[15, 5, 0]],
    flicker_pairs: [[0, 1, 100, true]],
    spots: { flicker_diff: [], flicker_same: [], reversed: [], hidden: [], loose: [], open_edges: [], cracks: [], facade: [] },
  }
}

/** `target` behind a Proxy, all the way down, that counts every read of its own data: the face
 *  ids, pairs and spots a deep watcher walks. Vue's own `__v_` flag checks are not counted. */
function countingReads<T extends object>(target: T): { file: T; reads: () => number } {
  let n = 0
  const wrap = (o: object): any => new Proxy(o, {
    get(t, key, receiver) {
      const v = Reflect.get(t, key, receiver)
      if (typeof key === 'string' && !key.startsWith('__v_')) n++
      return v !== null && typeof v === 'object' ? wrap(v) : v
    },
  })
  return { file: wrap(target), reads: () => n }
}

describe('useErrorFiles', () => {
  it('redraws when a kind, Isolate or Blink is toggled', async () => {
    const redraw = vi.fn()
    const { errorFilter, errorsBefore } = useErrorFiles(redraw)
    errorsBefore.value = makeFile()
    await nextTick()
    redraw.mockClear()

    errorFilter.enabled.loose = true
    await nextTick()
    expect(redraw).toHaveBeenCalledTimes(1)
    errorFilter.isolate = true
    await nextTick()
    expect(redraw).toHaveBeenCalledTimes(2)
    errorFilter.blink = true
    await nextTick()
    expect(redraw).toHaveBeenCalledTimes(3)
  })

  it('redraws when a file arrives, is replaced or is dropped', async () => {
    const redraw = vi.fn()
    const { errorsBefore, errorsAfter } = useErrorFiles(redraw)
    errorsBefore.value = makeFile()
    await nextTick()
    expect(redraw).toHaveBeenCalledTimes(1)
    errorsAfter.value = makeFile()
    await nextTick()
    expect(redraw).toHaveBeenCalledTimes(2)
    errorsBefore.value = makeFile()
    await nextTick()
    expect(redraw).toHaveBeenCalledTimes(3)
    errorsBefore.value = null
    await nextTick()
    expect(redraw).toHaveBeenCalledTimes(4)
  })

  it('keeps a file as it came: no reactive proxy around its hundred thousand values', () => {
    const { errorsBefore } = useErrorFiles(() => {})
    const file = makeFile()
    errorsBefore.value = file
    expect(errorsBefore.value).toBe(file)
    expect(isProxy(errorsBefore.value)).toBe(false)
  })

  it('does not walk either file when only the filter changes (review I1: 0.8 s a click on CHTM)', async () => {
    const before = countingReads(makeFile())
    const after = countingReads(makeFile())
    const { errorFilter, errorsBefore, errorsAfter } = useErrorFiles(() => {})
    errorsBefore.value = before.file
    errorsAfter.value = after.file
    await nextTick()
    const readsBefore = before.reads(), readsAfter = after.reads()

    errorFilter.enabled.hidden = true
    errorFilter.isolate = true
    errorFilter.blink = true
    await nextTick()

    expect(before.reads() - readsBefore).toBe(0)
    expect(after.reads() - readsAfter).toBe(0)
  })
})
