export interface ResultDescription {
  heading: string
  statusText: string
  guardLine: string
  guardPassed: boolean
  isRolledBack: boolean
  rolledBackReason?: string
  backfacePx?: number
  borderShiftPx?: number
  skpSummary?: string
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
  const skpSummary = report.skp_summary || report.skp_path

  return {
    heading,
    statusText: guardPassed ? 'Completed' : 'Failed',
    guardLine,
    guardPassed,
    isRolledBack,
    rolledBackReason,
    backfacePx,
    borderShiftPx,
    skpSummary,
  }
}
