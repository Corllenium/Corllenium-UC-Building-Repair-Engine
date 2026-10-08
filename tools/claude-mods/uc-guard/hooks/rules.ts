// uc-guard's rules: each returns the reason a tool call breaks an AGENTS.md rule, or undefined.
// Shell commands are read as words, segment by segment; the checks are heuristics that catch the
// mistakes past sessions made, not a full shell parser.

type Shell = 'bash' | 'ps'
// depth: how many parentheses enclose the segment; scopes: their ids, outermost first (each `(` gets a new id)
type Segment = { words: string[]; depth: number; scopes: number[] }

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
    'the secret files: the Jev plan (2026-10-08, "The secret") says agents never read .env* files, and the controller\'s ruling adds never writing them; the same holds for auth.json and anything under Corllenium-Phone-session-Config. Code reads keys at run time.',
} as const

const SOURCE_MARKERS = ['projects/uc environment building', 'projects/uc/02-sketchup/current', 'checkpoint-17-backup']
const RESULT_MARKERS = ['obj fixed result', 'model fixer engine files/04-coloring', 'model fixer engine files/05-fixing']
const VERIFIED = /(^|\/)\.claude\/worktrees\/verified(\/|$)/
const PHONE_CONFIG = 'corllenium-phone-session-config'
const SAFE_ENV = new Set(['.env.example', '.env.sample', '.env.template'])

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
  'rg', 'select-string', 'ii', 'invoke-item', 'start', 'explorer', 'echo', 'printf', 'write-output', 'write-host',
])
const GIT_READS = new Set(['log', 'show', 'diff', 'status', 'blame', 'ls-files', 'ls-tree', 'grep', 'check-ignore', 'shortlog'])
const PATTERN_VERBS = new Set(['grep', 'egrep', 'rg', 'sed', 'awk', 'select-string', 'sls', 'findstr', 'git'])
const FIND_WRITES = new Set(['-delete', '-exec', '-execdir', '-ok', '-okdir'])
const CD_BASH = new Set(['cd', 'pushd', 'popd'])
const CD_PS = new Set(['cd', 'chdir', 'set-location', 'sl', 'push-location', 'pushd', 'pop-location', 'popd'])
const WRAPPERS = new Set([
  'sudo', 'command', 'builtin', 'exec', 'time', 'nohup', 'env', '&', '.', '{', '}', '!',
  'if', 'then', 'else', 'elif', 'while', 'until', 'do',
])
const MESSAGE_FLAGS = new Set(['-m', '--message', '-t', '--title', '--body'])
const FILE_TOOLS = new Set(['Read', 'Write', 'Edit', 'NotebookEdit', 'MultiEdit'])
const SHELL_TOOLS: Record<string, Shell> = { Bash: 'bash', Monitor: 'bash', PowerShell: 'ps' }
const FIXER_CONTAINER = /^fixer-(api|web|db)$/
const COMPOSE_VALUE_OPTS = new Set([
  '-f', '--file', '-p', '--project-name', '--profile', '--env-file', '--project-directory', '--ansi', '--parallel', '--progress',
])
const COMPOSE_SUBS = new Set([
  'up', 'down', 'restart', 'stop', 'rm', 'kill', 'start', 'pause', 'unpause', 'create', 'run', 'exec', 'logs', 'ps',
  'build', 'pull', 'push', 'config', 'images', 'ls', 'top', 'events', 'port', 'cp', 'version', 'wait', 'watch',
])
const COMPOSE_WRITES = new Set(['up', 'down', 'restart', 'stop', 'rm', 'kill', 'start', 'pause'])
const PSQL_VALUE_OPTS = new Set(['-U', '--username', '-h', '--host', '-p', '--port', '-c', '--command', '-f', '--file', '-v', '--set', '--variable', '-P', '--pset', '-o', '--output', '-T', '-L', '--log-file'])

const norm = (s: string) =>
  s.replace(/\\ /g, ' ').replace(/\\/g, '/').replace(/^\/([a-z])\//i, '$1:/').replace(/\/+/g, '/').toLowerCase()
const has = (s: string, markers: string[]) => markers.some(m => norm(s).includes(m))
const base = (s: string) => norm(s).split('/').pop() ?? ''
const pathLike = (s: string) => /[/\\]/.test(s)

// A word that names a secret file. A word starting with `\.` is a regex escape, not a path.
const isSecretPath = (s: string): boolean => {
  if (s.startsWith('\\.')) return false
  const b = base(s)
  if (b === 'auth.json' || b === '.env' || b === '.env*') return true
  if (b.startsWith('.env.') && !SAFE_ENV.has(b)) return true
  // the folder's bare name is often a search pattern (grep, git log); a path to it is a read
  return pathLike(s) && norm(s).includes(PHONE_CONFIG)
}
const verb = (w: string | undefined) => (w === undefined ? undefined : base(w).replace(/\.exe$/, ''))

// Drops heredoc bodies so their text is never read as commands. A here-string (<<<) is not a heredoc.
function stripHeredocs(cmd: string): string {
  const out: string[] = []
  let end: string | undefined
  for (const line of cmd.split('\n')) {
    if (end !== undefined) {
      if (line.trim() === end) end = undefined
      continue
    }
    out.push(line)
    const m = /(?<!<)<<(?!<)-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1/.exec(line)
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
  const scopes: number[] = []
  let opened = 0
  let quote: string | null = null
  const endWord = () => {
    if (inWord) words.push(word)
    word = ''
    inWord = false
  }
  const endSegment = () => {
    endWord()
    if (words.length) out.push({ words, depth: scopes.length, scopes: [...scopes] })
    words = []
  }
  for (let i = 0; i < cmd.length; i++) {
    const c = cmd[i] ?? ''
    const n = cmd[i + 1] ?? ''
    if (quote) {
      if (c === quote) quote = null
      else if (shell === 'bash' && quote === '"' && c === '\\' && '"\\$`'.includes(n)) word += cmd[++i] ?? ''
      else if (shell === 'ps' && quote === '"' && c === '`') word += cmd[++i] ?? ''
      else word += c
      continue
    }
    if (c === "'" || c === '"') {
      quote = c
      inWord = true
      continue
    }
    if (shell === 'bash' && c === '\\' && n !== '.') {
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
      scopes.push(++opened)
      continue
    }
    if (c === ')') {
      endSegment()
      scopes.pop()
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

// The command words of a segment, past variable assignments, wrappers like sudo and shell keywords.
function commandWords(words: string[]): string[] {
  const i = words.findIndex(w => !/^[A-Za-z_][A-Za-z0-9_]*=/.test(w) && !WRAPPERS.has(w))
  return i < 0 ? [] : words.slice(i)
}

// Words that may name files: a git or gh message value (-m "...") is prose, not a path.
// Other commands keep every word (cp -t and mv -t take a directory).
function fileWords(words: string[]): string[] {
  const v = verb(words[0])
  if (v !== 'git' && v !== 'gh') return words
  const out: string[] = []
  for (let k = 0; k < words.length; k++) {
    const w = words[k] ?? ''
    if (MESSAGE_FLAGS.has(w)) {
      k++
      continue
    }
    if (/^--(message|title|body)=/.test(w)) continue
    out.push(w)
  }
  return out
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
  // -t names the target for cp, mv and install only (rsync -t keeps modification times)
  const targetFlag = (a: string) => a === '--target-directory' || (a === '-t' && ['cp', 'mv', 'install'].includes(v))
  const d = args.findIndex(a => /^-destination$/i.test(a) || targetFlag(a))
  if (d >= 0) return args[d + 1]
  const eq = args.find(a => a.startsWith('--target-directory='))
  if (eq !== undefined) return eq.slice('--target-directory='.length)
  const p = positional(args)
  return v === 'robocopy' || v === 'xcopy' ? p[1] : p[p.length - 1]
}

const findWrites = (v: string | undefined, args: string[]) => v === 'find' && args.some(a => FIND_WRITES.has(a))

function writesTo(seg: string[], markers: string[]): boolean {
  const [first, ...args] = seg
  const v = verb(first)
  if (redirectTargets(seg).some(t => has(t, markers))) return true
  if (v === undefined) return false
  if (WRITE_VERBS.has(v) || findWrites(v, args)) return args.some(a => has(a, markers))
  if (v === 'sed' && args.some(a => /^-i|^--in-place/.test(a))) return args.some(a => has(a, markers))
  if (COPY_VERBS.has(v)) {
    const dest = copyDestination(v, args)
    return dest !== undefined && has(dest, markers)
  }
  return false
}

// A result-folder word: a path, or the folder's own name, also as an option value (--out=...).
const namesResult = (word: string): boolean =>
  [word, word.split('=').pop() ?? ''].some(w => {
    if (!has(w, RESULT_MARKERS)) return false
    const n = norm(w)
    return pathLike(w) || RESULT_MARKERS.some(m => n === m || n.startsWith(`${m}/`))
  })

function gitSub(args: string[]): { sub: string | undefined; rest: string[] } {
  let i = 0
  for (let a = args[i]; a !== undefined && a.startsWith('-'); a = args[i]) {
    i += ['-C', '-c', '--git-dir', '--work-tree', '--namespace'].includes(a) ? 2 : 1
  }
  return { sub: args[i], rest: args.slice(i + 1) }
}

function gitReason(args: string[]): string | undefined {
  const { sub, rest } = gitSub(args)
  const shortHas = (a: string, f: string) => /^-[A-Za-z]+$/.test(a) && a.includes(f)
  if (sub === 'add' && rest.some(a => ['.', './', '.\\', ':/', '--all', '-u', '--update'].includes(a) || shortHas(a, 'A')))
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

function composeSub(args: string[]): string | undefined {
  for (let k = 0; k < args.length; k++) {
    const a = args[k] ?? ''
    if (COMPOSE_VALUE_OPTS.has(a)) {
      k++
      continue
    }
    if (a.startsWith('-')) continue
    if (COMPOSE_SUBS.has(a)) return a
  }
  return undefined
}

// A psql database argument that names the live database: the bare name, a URI, or conninfo.
const isLiveDb = (a: string) =>
  a === 'fixer' || /^postgres(ql)?:\/\/.*\/fixer(\?.*)?$/.test(a) || /(^|\s)dbname=fixer(\s|$)/.test(a)

function psqlTargetsLive(args: string[]): boolean {
  let firstPositional: string | undefined
  for (let k = 0; k < args.length; k++) {
    const a = args[k] ?? ''
    if (a === '-d' || a === '--dbname') {
      if (isLiveDb(args[k + 1] ?? '')) return true
      k++
      continue
    }
    if (PSQL_VALUE_OPTS.has(a)) {
      k++
      continue
    }
    if (a.startsWith('--dbname=') && isLiveDb(a.slice('--dbname='.length))) return true
    if (/^-d./.test(a) && isLiveDb(a.slice(2))) return true
    if (!a.startsWith('-') && firstPositional === undefined) firstPositional = a
  }
  return firstPositional !== undefined && isLiveDb(firstPositional)
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
    const sub = composeSub(args)
    if (sub !== undefined && COMPOSE_WRITES.has(sub)) return REASONS.live
  } else if (v === 'docker') {
    if (args[0] === 'container') args = args.slice(1)
    if (['restart', 'stop', 'rm', 'kill', 'start', 'pause', 'update', 'rename'].includes(args[0] ?? '') && args.some(a => FIXER_CONTAINER.test(a)))
      return REASONS.live
  }
  const p = seg.findIndex(w => verb(w) === 'psql')
  if (p >= 0 && psqlTargetsLive(seg.slice(p + 1))) return REASONS.live
  return undefined
}

function resultsReason(segs: Segment[]): string | undefined {
  // the subshell that did `cd <verified>` (0: top level); the exemption holds only inside it
  let verifiedScope: number | undefined
  for (const s of segs) {
    const seg = commandWords(s.words)
    const v = verb(seg[0])
    const args = seg.slice(1)
    if (v !== undefined && (CD_BASH.has(v) || CD_PS.has(v)) && VERIFIED.test(norm(args[0] ?? '')))
      verifiedScope = s.scopes[s.scopes.length - 1] ?? 0
    const inVerified = verifiedScope !== undefined && (verifiedScope === 0 || s.scopes.includes(verifiedScope))
    const words = fileWords(seg)
    const touched = words.some(namesResult) || redirectTargets(seg).some(t => has(t, RESULT_MARKERS))
    if (!touched || inVerified) continue
    if (v !== undefined && COPY_VERBS.has(v)) {
      const dest = copyDestination(v, args)
      const sources = positional(args).filter(a => a !== dest)
      if (sources.length > 0 && sources.every(a => VERIFIED.test(norm(a)))) continue
    }
    const gitRead = v === 'git' && GIT_READS.has(gitSub(args).sub ?? '')
    const readOnly =
      v === undefined || gitRead || (READ_VERBS.has(v) && !findWrites(v, args) && !redirectTargets(seg).some(t => has(t, RESULT_MARKERS)))
    if (!readOnly) return REASONS.results
  }
  return undefined
}

// The engine reads only the TYPESAFE_API_KEY line of the file given to `python -m engine.cli ... --env-file`
// (owner decision 2026-10-08: code reads keys at run time), so that one value is not an agent reading a secret.
// Only when the command itself is a Python interpreter whose module is engine.cli: options such as -u may come
// first, but no -c and no script.
const PYTHONS = new Set(['python', 'python3', 'py', '$py'])
function engineKeyFileDropped(words: string[]): string[] {
  if (!PYTHONS.has(verb(words[0]) ?? '')) return words
  let i = 1
  for (let w = words[i]; w !== undefined && w.startsWith('-') && w !== '-m' && w !== '-c'; w = words[i]) i++
  if (words[i] !== '-m' || words[i + 1] !== 'engine.cli') return words
  return words.filter((w, k) => !(k > i + 1 && (w.startsWith('--env-file=') || words[k - 1] === '--env-file')))
}

function shellReason(command: string, shell: Shell): string | undefined {
  const segs = segments(command, shell)

  for (const s of segs) {
    const seg = commandWords(s.words)
    const words = engineKeyFileDropped(fileWords(seg))
    // `\.env` is a regex escape for a pattern tool, but to cat it is just .env
    const unescape = PATTERN_VERBS.has(verb(seg[0]) ?? '') ? (w: string) => w : (w: string) => w.replace(/^\\(?=\.)/, '')
    if (
      words
        .map(unescape)
        .some(w => isSecretPath(w) || isSecretPath(w.split('=').pop() ?? '') || isSecretPath(w.replace(/^\d*[<>]+/, '')))
    )
      return REASONS.secret
    // a path inside code passed to an interpreter, e.g. python -c "open('.env')"
    if (words.some(w => /['"]([^'"\s]*[/\\])?\.env(\.local)?['"]/.test(w) && /\(/.test(w))) return REASONS.secret
  }

  for (const s of segs) {
    if (writesTo(commandWords(s.words), SOURCE_MARKERS)) return REASONS.source
  }

  const results = resultsReason(segs)
  if (results) return results

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
  const shell = SHELL_TOOLS[tool]
  if (shell !== undefined) return shellReason(str('command') ?? '', shell)
  if (tool === 'Grep' || tool === 'Glob') {
    const p = str('path')
    const g = str('glob') ?? (tool === 'Glob' ? str('pattern') : undefined)
    return (p !== undefined && isSecretPath(p)) || (g !== undefined && isSecretPath(g)) ? REASONS.secret : undefined
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
