export interface ResultDescription {
  heading: string
  statusText: string
  runPassed: boolean
  failedInvariants: string[]
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
  solidifySummary?: {
    skirtsAdded?: number
    bottomsAdded?: number
    inventedVertices?: number
    sidePiecesReplaced?: number
    sidesRebuiltEdges?: number
    capGuardPassed?: boolean
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
      runPassed: false,
      failedInvariants: [],
      guardLine: 'Guard not run',
      guardPassed: false,
      isRolledBack: false,
      error: err,
    }
  }

  const invariants = report.invariants || {}
  const failedInvariants: string[] = []
  if (typeof invariants === 'object') {
    for (const [key, val] of Object.entries(invariants)) {
      if (val === false) failedInvariants.push(key)
    }
  }

  const guard = report.guard_final || {}
  const totals = guard.totals
  const guardPassed = Boolean(guard.passed ?? report.guard_passed ?? true)

  const runPassed = typeof report.passed === 'boolean'
    ? report.passed
    : (failedInvariants.length === 0 && guardPassed)
  const statusText = runPassed ? 'Completed' : 'Failed'

  const mr = report.merge_report || {}
  const isRolledBack = Boolean(mr.rolled_back)
  const rolledBackReason = mr.rolled_back_reason || (isRolledBack ? 'unknown' : undefined)

  const heading = isRolledBack
    ? `INSIDE REMOVED, FACES FLIPPED · merge rolled back (${rolledBackReason})`
    : 'INSIDE REMOVED, FACES FLIPPED, FLAT REGIONS MERGED'

  const guardStatus = guardPassed ? 'Guard PASSED' : 'Guard FAILED'
  let guardLine: string
  if (!totals || typeof totals !== 'object') {
    guardLine = `${guardStatus} (totals not reported)`
  } else {
    const holesStr = typeof totals.holes === 'number' ? `${totals.holes} holes` : 'holes not reported'
    const movedVal = (typeof totals.moved_other === 'number' || typeof totals.moved_same_flat === 'number')
      ? (totals.moved_other ?? 0) + (totals.moved_same_flat ?? 0)
      : undefined
    const movedStr = typeof movedVal === 'number' ? `${movedVal} moved` : 'moved not reported'
    const matChangedStr = typeof totals.material_changed === 'number' ? `${totals.material_changed} mat changed` : 'mat changed not reported'
    const edgeFlickerStr = typeof totals.edge_flicker === 'number' ? `${totals.edge_flicker} edge flicker` : 'edge flicker not reported'
    const grownStr = typeof totals.grown === 'number' ? `${totals.grown} grown` : 'grown not reported'

    guardLine = `${guardStatus} (${holesStr}, ${movedStr}, ${matChangedStr}, ${edgeFlickerStr}, ${grownStr})`
  }

  let backfacePx: number | undefined
  if (typeof report.backface_px === 'number') {
    backfacePx = report.backface_px
  } else if (report.backface_px && typeof report.backface_px.final === 'object' && typeof report.backface_px.final.total === 'number') {
    backfacePx = report.backface_px.final.total
  } else if (report.backface_px && typeof report.backface_px.shipped === 'object' && typeof report.backface_px.shipped.total === 'number') {
    backfacePx = report.backface_px.shipped.total
  } else if (report.backface_px && typeof report.backface_px.final === 'number') {
    backfacePx = report.backface_px.final
  } else if (report.backface_px && typeof report.backface_px.shipped === 'number') {
    backfacePx = report.backface_px.shipped
  }

  const borderShiftPx = totals && typeof totals.border_shift === 'number' ? totals.border_shift : undefined
  const zfightTie = totals && typeof totals.zfight_tie === 'number' ? totals.zfight_tie : undefined
  const crackClosed = totals && typeof totals.crack_closed === 'number' ? totals.crack_closed : undefined

  let edgeFlickerBreakdown: ResultDescription['edgeFlickerBreakdown'] | undefined
  if (totals && typeof totals.edge_flicker === 'number') {
    edgeFlickerBreakdown = {
      total: totals.edge_flicker,
      hole: totals.edge_flicker_hole ?? 0,
      moved: totals.edge_flicker_moved ?? 0,
      material: totals.edge_flicker_material ?? 0,
      grown: totals.edge_flicker_grown ?? 0,
    }
  }

  let solidifySummary: ResultDescription['solidifySummary'] | undefined
  const sr = report.solidify_report
  if (sr && typeof sr === 'object') {
    solidifySummary = {
      skirtsAdded: typeof sr.skirts_added === 'number' ? sr.skirts_added : undefined,
      bottomsAdded: typeof sr.bottoms_added === 'number' ? sr.bottoms_added : undefined,
      inventedVertices: typeof sr.invented_vertices === 'number' ? sr.invented_vertices : undefined,
      sidePiecesReplaced: typeof sr.side_pieces_replaced === 'number' ? sr.side_pieces_replaced : undefined,
      sidesRebuiltEdges: sr.sides_rebuilt && typeof sr.sides_rebuilt.edges === 'number' ? sr.sides_rebuilt.edges : undefined,
      capGuardPassed: typeof sr.cap_guard_passed === 'boolean' ? sr.cap_guard_passed : undefined,
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
    statusText,
    runPassed,
    failedInvariants,
    guardLine,
    guardPassed,
    isRolledBack,
    rolledBackReason,
    backfacePx,
    borderShiftPx,
    zfightTie,
    crackClosed,
    edgeFlickerBreakdown,
    solidifySummary,
    guardMergeAttempt,
    skpSummary,
    skpPath,
    skpWritten,
    skpReason,
  }
}
