// uc-guard's rules: each returns the reason a tool call breaks an AGENTS.md rule, or undefined.
// Shell commands are read as words, segment by segment; the checks are heuristics that catch the
// mistakes past sessions made, not a full shell parser.

type Shell = 'bash' | 'ps'
type Segment = { words: string[]; depth: number }

export const REASONS = {
  source:
    'AGENTS.md §3 "Never touch" (and the §2 table): the CHECKPOINT-17 export (UC ENVIRONMENT BUILDING), the master (UC\\02-SKETCHUP\\current) and the backup (CHECKPOINT-17-BACKUP) are read-only; read the export only through engine/io/snapshot.py.',
  results:
    'AGENTS.md §3: OBJ FIXED RESULT and MODEL FIXER ENGINE FILES\\04-COLORING and \\05-FIXING take only files built from committed code, published from .claude/worktrees/verified; run the publish from there.',
  cdBash:
    'AGENTS.md §8 (no bare cd): a top-level cd moves the shared working directory; use ( cd "<dir>" && ... ) or git -C "<dir>".',
  cdPs:
    'AGENTS.md §8 (no bare cd): Set-Location moves the shared working directory, and PowerShell parentheses do not scope it; use absolute paths or git -C "<dir>".',
  git:
    'AGENTS.md §3 "Shared working tree": stage files by name; never git add -A / . / --all / -u, git commit -a, a git stash without push -m, or a force push.',
  live:
    'AGENTS.md §3 "Never touch": the live containers fixer-api, fixer-web and fixer-db and the live database fixer are the owner\'s; restarting them or writing to fixer needs his OK (HANDOFF §8).',
  secret:
    'owner rule (Jev plan 2026-10-08, "The secret"): agents never read or write .env, .env.local, auth.json or anything under Corllenium-Phone-session-Config; code reads keys at run time.',
} as const

const SOURCE_MARKERS = ['projects/uc environment building', 'projects/uc/02-sketchup/current', 'checkpoint-17-backup']
const RESULT_MARKERS = ['obj fixed result', 'model fixer engine files/04-coloring', 'model fixer engine files/05-fixing']
const VERIFIED_MARKER = 'worktrees/verified'
const PHONE_CONFIG = 'corllenium-phone-session-config'

const WRITE_VERBS = new Set([
  'rm', 'rmdir', 'unlink', 'shred', 'mv', 'touch', 'mkdir', 'tee', 'truncate', 'dd', 'chmod', 'chown', 'ln',
  'del', 'erase', 'rd', 'move', 'rename', 'ren', 'md',
  'remove-item', 'ri', 'move-item', 'mi', 'new-item', 'ni', 'set-content', 'sc', 'add-content', 'ac', 'out-file',
  'clear-content', 'clc', 'rename-item', 'rni', 'tee-object', 'set-itemproperty', 'sp',
])
const COPY_VERBS = new Set(['cp', 'copy', 'copy-item', 'cpi', 'install', 'rsync', 'scp', 'robocopy', 'xcopy'])
const READ_VERBS = new Set([
  'ls', 'dir', 'gci', 'get-childitem', 'cat', 'type', 'gc', 'get-content', 'head', 'tail', 'less', 'more', 'find',
  'stat', 'file', 'test-path', 'du', 'wc', 'tree', 'sha256sum', 'md5sum', 'get-filehash', 'get-item', 'gi', 'grep',
  'rg', 'select-string', 'ii', 'invoke-item', 'start', 'explorer',
])
const CD_BASH = new Set(['cd', 'pushd', 'popd'])
const CD_PS = new Set(['cd', 'chdir', 'set-location', 'sl', 'push-location', 'pushd', 'pop-location', 'popd'])
const WRAPPERS = new Set(['sudo', 'command', 'exec', 'time', 'nohup', 'env', '&', '.', '{', '}'])
const FILE_TOOLS = new Set(['Read', 'Write', 'Edit', 'NotebookEdit', 'MultiEdit'])
const FIXER_CONTAINER = /^fixer-(api|web|db)$/

const norm = (s: string) =>
  s.replace(/\\ /g, ' ').replace(/\\/g, '/').replace(/^\/([a-z])\//i, '$1:/').replace(/\/+/g, '/').toLowerCase()
const has = (s: string, markers: string[]) => markers.some(m => norm(s).includes(m))
const base = (s: string) => norm(s).split('/').pop() ?? ''
const isSecretPath = (s: string) => {
  const b = base(s)
  return b === '.env' || b === '.env.local' || b === 'auth.json' || norm(s).includes(PHONE_CONFIG)
}
const verb = (w: string | undefined) => (w === undefined ? undefined : base(w).replace(/\.exe$/, ''))

// Drops heredoc bodies so their text is never read as commands.
function stripHeredocs(cmd: string): string {
  const out: string[] = []
  let end: string | undefined
  for (const line of cmd.split('\n')) {
    if (end !== undefined) {
      if (line.trim() === end) end = undefined
      continue
    }
    out.push(line)
    const m = /<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1/.exec(line)
    if (m) end = m[2]
  }
  return out.join('\n')
}

// Splits a command into segments (at ; & && | || newlines and parentheses), each a list of words
// with quotes removed, and the parenthesis depth it sits at.
function segments(command: string, shell: Shell): Segment[] {
  const cmd = shell === 'bash' ? stripHeredocs(command) : command
  const out: Segment[] = []
  let words: string[] = []
  let word = ''
  let inWord = false
  let depth = 0
  let quote: string | null = null
  const endWord = () => {
    if (inWord) words.push(word)
    word = ''
    inWord = false
  }
  const endSegment = () => {
    endWord()
    if (words.length) out.push({ words, depth })
    words = []
  }
  for (let i = 0; i < cmd.length; i++) {
    const c = cmd[i]
    const n = cmd[i + 1] ?? ''
    if (quote) {
      if (c === quote) quote = null
      else if (shell === 'bash' && quote === '"' && c === '\\' && '"\\$`'.includes(n)) word += cmd[++i]
      else if (shell === 'ps' && quote === '"' && c === '`') word += cmd[++i] ?? ''
      else word += c
      continue
    }
    if (c === "'" || c === '"') {
      quote = c
      inWord = true
      continue
    }
    if (shell === 'bash' && c === '\\') {
      word += n
      inWord = true
      i++
      continue
    }
    if (shell === 'ps' && c === '`') {
      word += n
      inWord = true
      i++
      continue
    }
    if (c === '(') {
      endSegment()
      depth++
      continue
    }
    if (c === ')') {
      endSegment()
      depth = Math.max(0, depth - 1)
      continue
    }
    const prev = cmd[i - 1] ?? ''
    if (c === '&' && (prev === '>' || prev === '<' || n === '>')) {
      word += c
      inWord = true
      continue
    }
    if (c === ';' || c === '\n' || c === '|' || c === '&') {
      endSegment()
      continue
    }
    if (c === ' ' || c === '\t' || c === '\r') {
      endWord()
      continue
    }
    word += c
    inWord = true
  }
  endSegment()
  return out
}

// The command words of a segment, past variable assignments and wrappers like sudo.
function commandWords(words: string[]): string[] {
  const i = words.findIndex(w => !/^[A-Za-z_][A-Za-z0-9_]*=/.test(w) && !WRAPPERS.has(w))
  return i < 0 ? [] : words.slice(i)
}

const redirectTargets = (words: string[]) => {
  const targets: string[] = []
  words.forEach((w, i) => {
    const target = /^\d*>>?(.*)$/.exec(w)?.[1]
    if (target === undefined || target.startsWith('&')) return
    const next = words[i + 1]
    if (target) targets.push(target)
    else if (next !== undefined) targets.push(next)
  })
  return targets
}

const positional = (args: string[]) => args.filter(a => !a.startsWith('-'))

function copyDestination(v: string, args: string[]): string | undefined {
  const d = args.findIndex(a => /^-destination$/i.test(a))
  if (d >= 0) return args[d + 1]
  const p = positional(args)
  return v === 'robocopy' || v === 'xcopy' ? p[1] : p[p.length - 1]
}

function writesTo(seg: string[], markers: string[]): boolean {
  const [first, ...args] = seg
  const v = verb(first)
  if (redirectTargets(seg).some(t => has(t, markers))) return true
  if (v === undefined) return false
  if (WRITE_VERBS.has(v)) return args.some(a => has(a, markers))
  if (v === 'sed' && args.some(a => /^-i|^--in-place/.test(a))) return args.some(a => has(a, markers))
  if (COPY_VERBS.has(v)) {
    const dest = copyDestination(v, args)
    return dest !== undefined && has(dest, markers)
  }
  return false
}

function gitReason(args: string[]): string | undefined {
  let i = 0
  for (let a = args[i]; a !== undefined && a.startsWith('-'); a = args[i]) {
    i += ['-C', '-c', '--git-dir', '--work-tree', '--namespace'].includes(a) ? 2 : 1
  }
  const sub = args[i]
  const rest = args.slice(i + 1)
  const shortHas = (a: string, f: string) => /^-[A-Za-z]+$/.test(a) && a.includes(f)
  if (sub === 'add' && rest.some(a => ['.', './', ':/', '--all', '-u', '--update'].includes(a) || shortHas(a, 'A')))
    return REASONS.git
  if (sub === 'commit') {
    const takesValue = new Set(['-m', '-F', '-C', '-c', '-t', '--message', '--file', '--author', '--date', '--template', '--fixup', '--squash'])
    let skip = false
    for (const a of rest) {
      if (skip) {
        skip = false
        continue
      }
      if (takesValue.has(a)) skip = true
      else if (a === '--all' || (shortHas(a, 'a') && !a.startsWith('-m'))) return REASONS.git
    }
  }
  if (sub === 'stash') {
    const first = rest[0]
    const action = first === undefined || first.startsWith('-') ? 'push' : first
    const named = rest.some(a => a === '-m' || a === '--message' || /^-m.|^--message=/.test(a))
    if (action === 'save' || action === 'clear' || (action === 'push' && !named)) return REASONS.git
  }
  if (sub === 'push' && rest.some(a => /^--force/.test(a) || shortHas(a, 'f') || a.startsWith('+'))) return REASONS.git
  return undefined
}

function liveReason(seg: string[]): string | undefined {
  const v = verb(seg[0])
  let args = seg.slice(1)
  let compose = v === 'docker-compose'
  if (v === 'docker' && args[0] === 'compose') {
    compose = true
    args = args.slice(1)
  }
  if (compose) {
    const sub = positional(args)[0]
    if (sub && ['up', 'down', 'restart', 'stop', 'rm', 'kill', 'start', 'pause'].includes(sub)) return REASONS.live
  } else if (v === 'docker') {
    if (args[0] === 'container') args = args.slice(1)
    if (['restart', 'stop', 'rm', 'kill', 'start', 'pause', 'update', 'rename'].includes(args[0] ?? '') && args.some(a => FIXER_CONTAINER.test(a)))
      return REASONS.live
  }
  const p = seg.findIndex(w => verb(w) === 'psql')
  if (p >= 0) {
    const a = seg.slice(p + 1)
    const live = a.some(
      (w, k) =>
        w === 'fixer' ||
        w === '-dfixer' ||
        /(^|\s)dbname=fixer(\s|$)/.test(w) ||
        /^--dbname=fixer$/.test(w) ||
        /\/fixer(\?.*)?$/.test(w) ||
        ((w === '-d' || w === '--dbname') && a[k + 1] === 'fixer'),
    )
    if (live) return REASONS.live
  }
  return undefined
}

function shellReason(command: string, shell: Shell): string | undefined {
  const segs = segments(command, shell)
  const all = segs.flatMap(s => s.words)
  const n = norm(command)

  if (n.includes(PHONE_CONFIG)) return REASONS.secret
  if (all.some(w => isSecretPath(w) || isSecretPath(w.split('=').pop() ?? '') || isSecretPath(w.replace(/^\d*[<>]+/, ''))))
    return REASONS.secret
  if (/['"/\\]\.env(\.local)?['"]/.test(command)) return REASONS.secret

  for (const s of segs) {
    const seg = commandWords(s.words)
    if (writesTo(seg, SOURCE_MARKERS)) return REASONS.source
  }

  if (all.some(w => has(w, RESULT_MARKERS)) && !n.includes(VERIFIED_MARKER)) {
    for (const s of segs) {
      const seg = commandWords(s.words)
      if (!seg.some(w => has(w, RESULT_MARKERS))) continue
      const v = verb(seg[0])
      const readOnly = v === undefined || (READ_VERBS.has(v) && redirectTargets(seg).length === 0)
      if (!readOnly) return REASONS.results
    }
  }

  for (const s of segs) {
    const seg = commandWords(s.words)
    const v = verb(seg[0])
    const live = liveReason(seg)
    if (live) return live
    if (v === 'git') {
      const g = gitReason(seg.slice(1))
      if (g) return g
    }
    if (shell === 'bash' && s.depth === 0 && v !== undefined && CD_BASH.has(v)) return REASONS.cdBash
    if (shell === 'ps' && v !== undefined && CD_PS.has(v)) return REASONS.cdPs
  }
  return undefined
}

export function check(tool: string, input: Record<string, unknown>): string | undefined {
  const str = (k: string) => (typeof input[k] === 'string' ? (input[k] as string) : undefined)
  if (tool === 'Bash') return shellReason(str('command') ?? '', 'bash')
  if (tool === 'PowerShell') return shellReason(str('command') ?? '', 'ps')
  if (tool === 'Grep' || tool === 'Glob') {
    const p = str('path')
    return p !== undefined && isSecretPath(p) ? REASONS.secret : undefined
  }
  if (FILE_TOOLS.has(tool)) {
    const p = str('file_path') ?? str('notebook_path')
    if (p === undefined) return undefined
    if (isSecretPath(p)) return REASONS.secret
    if (tool === 'Read') return undefined
    if (has(p, SOURCE_MARKERS)) return REASONS.source
    if (has(p, RESULT_MARKERS) && !norm(p).includes('/.claude/worktrees/')) return REASONS.results
  }
  return undefined
}
