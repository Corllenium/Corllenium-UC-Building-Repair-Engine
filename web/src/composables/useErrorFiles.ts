import { reactive, shallowRef, watch } from 'vue'
import { defaultFilter, type ErrorsFile } from '../utils/errorLayers'

/** The workspace's two errors files (BEFORE and AFTER) and the filter drawn over them, with one
 *  watcher that calls `redraw` whenever the filter or either file changes.
 *
 *  The files are `shallowRef`s and the watcher is not `deep` (review I1). A file is never changed
 *  in place, only replaced whole, so its identity is all the watcher needs; a deep `ref` and a
 *  `deep: true` watcher walked every face id, pair and spot of BOTH files on every legend,
 *  Isolate or Blink click, about 0.8 s a click on CHTM. `errorFilter` is `reactive`, and Vue still
 *  watches a reactive source in the array deeply, so every checkbox in it still redraws. */
export function useErrorFiles(redraw: () => void) {
  const errorFilter = reactive(defaultFilter())
  const errorsBefore = shallowRef<ErrorsFile | null>(null)
  const errorsAfter = shallowRef<ErrorsFile | null>(null)
  watch([errorFilter, errorsBefore, errorsAfter], redraw)
  return { errorFilter, errorsBefore, errorsAfter }
}
