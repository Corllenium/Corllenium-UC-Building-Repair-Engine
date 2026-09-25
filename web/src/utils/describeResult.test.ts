import { describe, it, expect } from 'vitest'
import { describeResult } from './describeResult'

describe('describeResult', () => {
  it('handles null or error reports', () => {
    const resNull = describeResult(null)
    expect(resNull.error).toBeDefined()
    expect(resNull.heading).toBe('Fix Run Failed')

    const resError = describeResult({ error: 'Engine segfault' })
    expect(resError.error).toBe('Engine segfault')
    expect(resError.heading).toBe('Fix Run Failed')
  })

  it('formats rolled-back merge heading and reason', () => {
    const report = {
      passed: true,
      merge_report: {
        rolled_back: true,
        rolled_back_reason: 'guard_failed',
      },
      guard_final: {
        passed: true,
        totals: {
          holes: 0,
          moved_other: 0,
          moved_same_flat: 0,
          material_changed: 0,
          edge_flicker: 12,
          border_shift: 4,
        },
      },
      backface_px: { final: 1200 },
      skp_summary: 'OBJ FIXED RESULT/model.fixed.skp (120 faces)',
    }

    const desc = describeResult(report)
    expect(desc.heading).toBe('INSIDE REMOVED, FACES FLIPPED · merge rolled back (guard_failed)')
    expect(desc.isRolledBack).toBe(true)
    expect(desc.rolledBackReason).toBe('guard_failed')
    expect(desc.guardPassed).toBe(true)
    expect(desc.guardLine).toContain('Guard PASSED')
    expect(desc.guardLine).toContain('0 holes')
    expect(desc.guardLine).toContain('0 moved')
    expect(desc.guardLine).toContain('0 mat changed')
    expect(desc.guardLine).toContain('12 edge flicker')
    expect(desc.borderShiftPx).toBe(4)
    expect(desc.backfacePx).toBe(1200)
    expect(desc.skpSummary).toBe('OBJ FIXED RESULT/model.fixed.skp (120 faces)')
  })

  it('formats successful unrolled merge heading and failed guard line', () => {
    const report = {
      passed: false,
      merge_report: {
        rolled_back: false,
      },
      guard_final: {
        passed: false,
        totals: {
          holes: 2,
          moved_other: 3,
          moved_same_flat: 1,
          material_changed: 1,
          edge_flicker: 40,
          border_shift: 0,
        },
      },
    }

    const desc = describeResult(report)
    expect(desc.heading).toBe('INSIDE REMOVED, FACES FLIPPED, FLAT REGIONS MERGED')
    expect(desc.isRolledBack).toBe(false)
    expect(desc.guardPassed).toBe(false)
    expect(desc.guardLine).toContain('Guard FAILED')
    expect(desc.guardLine).toContain('2 holes')
    expect(desc.guardLine).toContain('4 moved')
    expect(desc.guardLine).toContain('1 mat changed')
    expect(desc.guardLine).toContain('40 edge flicker')
  })
})
