import { reactive, shallowRef, watch } from 'vue'
import { defaultFilter, type ErrorsFile } from '../utils/errorLayers'

/** The banner line for an errors file that belongs to another model (review M3). */
export const MISMATCH_MESSAGE = 'errors file does not match this model; press Find errors'

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

  /** `file` if it fits the model loaded beside it, else null (review M3). A file whose `n_faces`
   *  is not that model's face count belongs to another model -- a version id reused after a
   *  database restore -- so nothing may be drawn from it: it is dropped from its panel, which then
   *  offers Find errors again, and reported once. `modelFaces` is null while no model is loaded. */
  function fitToModel(file: ErrorsFile | null, modelFaces: number | null,
    report: (message: string) => void): ErrorsFile | null {
    if (!file || modelFaces === null || file.n_faces === modelFaces) return file
    if (errorsBefore.value === file) errorsBefore.value = null
    if (errorsAfter.value === file) errorsAfter.value = null
    report(MISMATCH_MESSAGE)
    return null
  }

  return { errorFilter, errorsBefore, errorsAfter, fitToModel }
}

/** An errors file is an optional overlay (review M1): a failed fetch goes to the banner and reads
 *  as no file, so it never stops the workspace loading its models. A 404 already reads as null. */
export async function errorsOrNull(fetching: Promise<ErrorsFile | null>, label: string,
  report: (message: string) => void): Promise<ErrorsFile | null> {
  try {
    return await fetching
  } catch (err: any) {
    report(`Loading errors failed for ${label}: ${err?.message || 'unknown error'}`)
    return null
  }
}
