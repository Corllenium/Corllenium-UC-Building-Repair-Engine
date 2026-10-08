import type { Register } from 'claude-code'
import { check } from './rules.ts'

// Denies tool calls that break UC MODEL FIXER's AGENTS.md rules; everything else passes unchanged.
export const register: Register = on => {
  on('tool.call', ($, e, next) => {
    const reason = check(e.tool, e as unknown as Record<string, unknown>)
    if (reason === undefined) return next(e)
    try {
      $.ui.toast(`uc-guard denied ${e.tool}: ${reason.split(':')[0]}`)
    } catch {
      // a toast is a courtesy; the deny stands without it
    }
    return { deny: `uc-guard: ${reason}` }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: 'uc-guard: its rule check failed, so the call is refused. Retry it or ask the owner.' },
  )
}
