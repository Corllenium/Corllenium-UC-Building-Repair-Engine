import type { FixRun } from '../api/client'

/**
 * Resolves the active run to display in the AFTER panel.
 *
 * If a fix run fails with an exception (status === 'failed' and no fixed_version_id),
 * reloadModel must NOT overwrite it with a previous fixed version's run or null.
 * When latestRun is null (e.g. on mount), the fetched run is used.
 */
export function resolveActiveRun(
  currentRun: FixRun | null,
  fetchedRun: FixRun | null
): FixRun | null {
  if (currentRun && currentRun.status === 'failed' && !currentRun.fixed_version_id) {
    if (!fetchedRun || currentRun.id >= fetchedRun.id) {
      return currentRun
    }
  }
  return fetchedRun
}

export async function loadVersionRunOnMount(
  fixedVersionId: number | undefined,
  fetchRun: (id: number) => Promise<FixRun>
): Promise<FixRun | null> {
  if (!fixedVersionId) return null
  try {
    return await fetchRun(fixedVersionId)
  } catch {
    return null
  }
}
