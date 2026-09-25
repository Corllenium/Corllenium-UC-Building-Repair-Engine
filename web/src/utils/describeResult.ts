export interface ResultDescription {
  heading: string
  statusText: string
  guardLine: string
  guardPassed: boolean
  isRolledBack: boolean
  rolledBackReason?: string
  backfacePx?: number
  borderShiftPx?: number
  zfightTie?: number
  crackClosed?: number
  edgeFlickerBreakdown?: {
    total: number
    hole: number
    moved: number
    material: number
    grown: number
  }
  guardMergeAttempt?: {
    passed: boolean
    holes?: number
    moved?: number
  }
  skpSummary?: string
  skpPath?: string
  skpWritten?: boolean
  skpReason?: string
  error?: string
}

export function describeResult(report: any): ResultDescription {
  if (!report || report.error) {
    const err = report?.error || 'Fix run failed or no report available'
    return {
      heading: 'Fix Run Failed',
      statusText: 'Failed',
      guardLine: 'Guard not run',
      guardPassed: false,
      isRolledBack: false,
      error: err,
    }
  }

  const mr = report.merge_report || {}
  const isRolledBack = Boolean(mr.rolled_back)
  const rolledBackReason = mr.rolled_back_reason || (isRolledBack ? 'unknown' : undefined)

  const heading = isRolledBack
    ? `INSIDE REMOVED, FACES FLIPPED · merge rolled back (${rolledBackReason})`
    : 'INSIDE REMOVED, FACES FLIPPED, FLAT REGIONS MERGED'

  const guard = report.guard_final || {}
  const totals = guard.totals || {}
  const holes = totals.holes ?? 0
  const movedOther = totals.moved_other ?? 0
  const movedSameFlat = totals.moved_same_flat ?? 0
  const moved = movedOther + movedSameFlat
  const matChanged = totals.material_changed ?? 0
  const edgeFlicker = totals.edge_flicker ?? 0

  const guardPassed = Boolean(guard.passed ?? report.passed ?? report.guard_passed)
  const guardStatus = guardPassed ? 'Guard PASSED' : 'Guard FAILED'
  const guardLine = `${guardStatus} (${holes} holes, ${moved} moved, ${matChanged} mat changed, ${edgeFlicker} edge flicker)`

  let backfacePx: number | undefined
  if (typeof report.backface_px === 'number') {
    backfacePx = report.backface_px
  } else if (report.backface_px && typeof report.backface_px.final === 'number') {
    backfacePx = report.backface_px.final
  } else if (report.backface_px && typeof report.backface_px.shipped === 'number') {
    backfacePx = report.backface_px.shipped
  }

  const borderShiftPx = typeof totals.border_shift === 'number' ? totals.border_shift : undefined
  const zfightTie = typeof totals.zfight_tie === 'number' ? totals.zfight_tie : undefined
  const crackClosed = typeof totals.crack_closed === 'number' ? totals.crack_closed : undefined

  let edgeFlickerBreakdown: ResultDescription['edgeFlickerBreakdown'] | undefined
  if (typeof totals.edge_flicker === 'number') {
    edgeFlickerBreakdown = {
      total: totals.edge_flicker,
      hole: totals.edge_flicker_hole ?? 0,
      moved: totals.edge_flicker_moved ?? 0,
      material: totals.edge_flicker_material ?? 0,
      grown: totals.edge_flicker_grown ?? 0,
    }
  }

  let guardMergeAttempt: ResultDescription['guardMergeAttempt'] | undefined
  if (report.guard_merge_attempt && typeof report.guard_merge_attempt === 'object') {
    const gmaTotals = report.guard_merge_attempt.totals || {}
    guardMergeAttempt = {
      passed: Boolean(report.guard_merge_attempt.passed),
      holes: gmaTotals.holes,
      moved: (gmaTotals.moved_same_flat ?? 0) + (gmaTotals.moved_other ?? 0),
    }
  }

  const skp = report.skp || {}
  const skpWritten = typeof skp.written === 'boolean' ? skp.written : undefined
  const skpPath = skp.copied_to || skp.path || report.skp_path
  const skpReason = skp.reason || skp.error
  const skpSummary = report.skp_summary || (skpPath ? `SketchUp file: ${skpPath}` : undefined)

  return {
    heading,
    statusText: guardPassed ? 'Completed' : 'Failed',
    guardLine,
    guardPassed,
    isRolledBack,
    rolledBackReason,
    backfacePx,
    borderShiftPx,
    zfightTie,
    crackClosed,
    edgeFlickerBreakdown,
    guardMergeAttempt,
    skpSummary,
    skpPath,
    skpWritten,
    skpReason,
  }
}
