import { describe, it, expect } from 'vitest'
import { describeResult } from './describeResult'

// Real engine report produced by engine.cli._build_report on box_with_partition(10.0)
const REAL_ENGINE_REPORT = {
  name: 'box_part',
  input_sha256: 'bf427b30419923c24a1b2fdceb370ab731e9572a0810284705238fe5f2359f40',
  profile: {
    n_dirs: 16,
    slit_threshold: 0.05,
    accept_slit: false,
    flat_texture_std: 8.0,
    solidify: true,
  },
  tris_before: 14,
  tris_reference: 14,
  tris_after: 12,
  solidify_report: {
    regions_processed: 1,
    skirts_added: 0,
    sides_rebuilt: { edges: 0, length: 0.0 },
    side_pieces_replaced: 0,
    bottoms_added: 0,
    invented_vertices: 0,
    cap_guard_passed: true,
  },
  materials_before: 1,
  materials_after: 1,
  n_hidden_candidates: 2,
  n_restored_by_guard: 0,
  n_removed_hidden: 2,
  n_removed_slit: 0,
  n_zero_area_dropped: 0,
  n_degenerate_restored: 0,
  n_flipped: 0,
  n_thin_sheets: 0,
  n_fragment_components: 1,
  n_removed_fragments: 0,
  n_removed_slivers: 0,
  n_restored_fragments: 0,
  n_refused_by_rays: 0,
  n_removed_folds: 0,
  backface_px: {
    input: { total: 1, per_view: [0, 1] },
    reference: { total: 1, per_view: [0, 1] },
    final: { total: 1, per_view: [0, 1] },
  },
  guard_after_removal: {
    passed: true,
    totals: {
      model_px: 7449943,
      holes: 0,
      material_changed: 0,
      moved_same_flat: 0,
      moved_other: 0,
      zfight_tie: 0,
      crack_closed: 0,
      edge_flicker: 0,
      border_shift: 0,
      grown: 0,
    },
  },
  guard_merge_attempt: {
    passed: true,
    totals: {
      model_px: 7449943,
      holes: 0,
      material_changed: 0,
      moved_same_flat: 0,
      moved_other: 0,
      zfight_tie: 0,
      crack_closed: 0,
      edge_flicker: 0,
      border_shift: 0,
      grown: 0,
    },
  },
  guard_final: {
    passed: true,
    totals: {
      model_px: 7449943,
      holes: 0,
      material_changed: 0,
      moved_same_flat: 0,
      moved_other: 0,
      zfight_tie: 0,
      crack_closed: 0,
      edge_flicker: 0,
      edge_flicker_hole: 0,
      edge_flicker_moved: 0,
      edge_flicker_material: 0,
      edge_flicker_grown: 0,
      border_shift: 0,
      grown: 0,
    },
  },
  strict_final: true,
  merge_report: {
    converged: true,
    rolled_back: false,
    rolled_back_reason: null,
    regions_merged: 6,
    tris_before: 12,
    tris_after: 12,
  },
  invariants: {
    material_count_same: true,
    bbox_same: true,
    area_not_grown: true,
    cap_guard_passed: true,
    guard_passed: true,
  },
  passed: true,
}

describe('describeResult', () => {
  it('handles null or error reports', () => {
    const resNull = describeResult(null)
    expect(resNull.error).toBeDefined()
    expect(resNull.heading).toBe('Fix Run Failed')
    expect(resNull.runPassed).toBe(false)
    expect(resNull.statusText).toBe('Failed')

    const resError = describeResult({ error: 'Engine segfault' })
    expect(resError.error).toBe('Engine segfault')
    expect(resError.heading).toBe('Fix Run Failed')
    expect(resError.runPassed).toBe(false)
    expect(resError.statusText).toBe('Failed')
  })

  it('correctly reports real engine report with pass verdict, backface total, and grown count', () => {
    const desc = describeResult(REAL_ENGINE_REPORT)
    expect(desc.heading).toBe('INSIDE REMOVED, FACES FLIPPED, FLAT REGIONS MERGED')
    expect(desc.isRolledBack).toBe(false)
    expect(desc.guardPassed).toBe(true)
    expect(desc.runPassed).toBe(true)
    expect(desc.statusText).toBe('Completed')
    expect(desc.failedInvariants).toEqual([])
    expect(desc.backfacePx).toBe(1)
    expect(desc.guardLine).toBe('Guard PASSED (0 holes, 0 moved, 0 mat changed, 0 edge flicker, 0 grown)')
  })

  it('marks run as failed and lists failing invariants even when guard visual pass is true', () => {
    const failedInvariantReport = {
      ...REAL_ENGINE_REPORT,
      invariants: {
        ...REAL_ENGINE_REPORT.invariants,
        bbox_same: false,
        cap_guard_passed: false,
      },
      passed: false,
    }

    const desc = describeResult(failedInvariantReport)
    expect(desc.guardPassed).toBe(true) // Visual guard passed
    expect(desc.runPassed).toBe(false)   // But overall run failed
    expect(desc.statusText).toBe('Failed')
    expect(desc.failedInvariants).toEqual(['bbox_same', 'cap_guard_passed'])
    expect(desc.guardLine).toContain('Guard PASSED')
  })

  it('formats rolled-back merge heading and reason from real report structure', () => {
    const rolledBackReport = {
      ...REAL_ENGINE_REPORT,
      merge_report: {
        ...REAL_ENGINE_REPORT.merge_report,
        rolled_back: true,
        rolled_back_reason: 'guard_failed',
      },
    }

    const desc = describeResult(rolledBackReport)
    expect(desc.heading).toBe('INSIDE REMOVED, FACES FLIPPED · merge rolled back (guard_failed)')
    expect(desc.isRolledBack).toBe(true)
    expect(desc.rolledBackReason).toBe('guard_failed')
  })

  it('surfaces grown pixels when guard fails on grown pixels', () => {
    const grownFailedReport = {
      ...REAL_ENGINE_REPORT,
      guard_final: {
        passed: false,
        totals: {
          holes: 0,
          moved_other: 0,
          moved_same_flat: 0,
          material_changed: 0,
          edge_flicker: 0,
          grown: 35,
        },
      },
      invariants: {
        ...REAL_ENGINE_REPORT.invariants,
        guard_passed: false,
      },
      passed: false,
    }

    const desc = describeResult(grownFailedReport)
    expect(desc.guardPassed).toBe(false)
    expect(desc.guardLine).toBe('Guard FAILED (0 holes, 0 moved, 0 mat changed, 0 edge flicker, 35 grown)')
  })

  it('prints not reported when guard totals are missing', () => {
    const missingTotalsReport = {
      ...REAL_ENGINE_REPORT,
      guard_final: {
        passed: false,
        totals: {
          holes: 1,
        },
      },
    }

    const desc = describeResult(missingTotalsReport)
    expect(desc.guardLine).toBe(
      'Guard FAILED (1 holes, moved not reported, mat changed not reported, edge flicker not reported, grown not reported)'
    )
  })

  it('formats guard totals (zfight_tie, crack_closed, flicker breakdown), guard_merge_attempt, and skp info', () => {
    const report = {
      ...REAL_ENGINE_REPORT,
      guard_final: {
        passed: true,
        totals: {
          ...REAL_ENGINE_REPORT.guard_final.totals,
          edge_flicker: 15,
          edge_flicker_hole: 5,
          edge_flicker_moved: 7,
          edge_flicker_material: 2,
          edge_flicker_grown: 1,
          zfight_tie: 3,
          crack_closed: 8,
          border_shift: 0,
          grown: 0,
        },
      },
      skp: {
        written: true,
        copied_to: 'OBJ FIXED RESULT/cube.fixed.skp',
        path: 'data/fixed/1/cube.fixed.skp',
      },
    }

    const desc = describeResult(report)
    expect(desc.zfightTie).toBe(3)
    expect(desc.crackClosed).toBe(8)
    expect(desc.edgeFlickerBreakdown).toEqual({
      total: 15,
      hole: 5,
      moved: 7,
      material: 2,
      grown: 1,
    })
    expect(desc.guardMergeAttempt?.passed).toBe(true)
    expect(desc.skpPath).toBe('OBJ FIXED RESULT/cube.fixed.skp')
    expect(desc.skpWritten).toBe(true)

    // And when skp skipped
    const skippedReport = {
      ...report,
      skp: {
        written: false,
        reason: 'SketchUp C API DLL not found',
      },
    }
    const descSkipped = describeResult(skippedReport)
    expect(descSkipped.skpWritten).toBe(false)
    expect(descSkipped.skpReason).toBe('SketchUp C API DLL not found')
  })

  it('reports skp copy_error when owner copy fails', () => {
    const report = {
      ...REAL_ENGINE_REPORT,
      skp: {
        written: true,
        path: 'data/fixed/1/cube.fixed.skp',
        copied_to: null,
        copy_error: '[Errno 13] Permission denied',
      },
    }
    const desc = describeResult(report)
    expect(desc.skpCopyError).toBe('[Errno 13] Permission denied')
    expect(desc.skpSummary).toContain('[Errno 13] Permission denied')
    expect(desc.skpSummary).toContain('previous file')
  })

  it('handles pre-branch reports (like v4) with missing merge_report as merge not reported', () => {
    const v4Report = {
      name: 'CHTM_SIDE_WALK_2nd_floor',
      tris_before: 4692,
      tris_after: 2656,
      passed: true,
      n_removed_hidden: 1819,
      n_restored_by_guard: 34,
      n_flipped: 844,
      n_zero_area_dropped: 217,
      one_sided_holes_before: 570046,
      one_sided_holes_after: 116041,
      guard_passed: true,
    }

    const desc = describeResult(v4Report)
    expect(desc.heading).toBe('INSIDE REMOVED, FACES FLIPPED · merge not reported')
    expect(desc.mergeReported).toBe(false)
    expect(desc.isRolledBack).toBe(false)
    expect(desc.runPassed).toBe(true)
    expect(desc.guardPassed).toBe(true)
    expect(desc.guardLine).toBe('Guard PASSED (totals not reported)')
  })

  it('reports guard not reported when neither guard_final nor guard_passed is present', () => {
    const noGuardReport = {
      name: 'test_model',
      passed: true,
      tris_before: 10,
      tris_after: 10,
    }

    const desc = describeResult(noGuardReport)
    expect(desc.guardPassed).toBe(false)
    expect(desc.guardLine).toBe('Guard not reported')
  })
})
