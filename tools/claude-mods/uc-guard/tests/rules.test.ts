import { describe, expect, test } from 'claude-code/testing'
import { check, REASONS } from '../hooks/rules.ts'

const ROOT = 'D:/PROJECTS/UC MODEL FIXER'
const WT = `${ROOT}/.claude/worktrees/P0-17`
const VERIFIED = `${ROOT}/.claude/worktrees/verified`
const CKPT17 = '/d/PROJECTS/UC ENVIRONMENT BUILDING/REQUIREMENTS/01-MODEL-EXPORT/CKPT17'

const bash = (command: string) => check('Bash', { command })
const ps = (command: string) => check('PowerShell', { command })

describe('rule 1: CHECKPOINT-17 export, master and backup are never written', () => {
  test('denies rm under the live export folder', () => {
    expect(bash(`rm -rf "${CKPT17}/x.obj"`)).toBe(REASONS.source)
  })
  test('denies Write into the master folder', () => {
    expect(check('Write', { file_path: 'D:\\PROJECTS\\UC\\02-SKETCHUP\\current\\a.skp', content: 'x' })).toBe(REASONS.source)
  })
  test('denies Remove-Item in the backup folder', () => {
    expect(ps(`Remove-Item "D:\\PROJECTS\\UC MODEL FIXER\\MODEL FIXER ENGINE FILES\\02-SKETCHUP-MODELS\\CHECKPOINT-17-BACKUP\\x.skp"`)).toBe(REASONS.source)
  })
  test('denies cp with the export folder as destination', () => {
    expect(bash('cp a.obj "D:/PROJECTS/UC ENVIRONMENT BUILDING/x.obj"')).toBe(REASONS.source)
  })
  test('denies a redirect into the master folder', () => {
    expect(bash('echo x > "/d/PROJECTS/UC/02-SKETCHUP/current/note.txt"')).toBe(REASONS.source)
  })
  test('denies find -delete and find -exec rm under the export (review finding 2)', () => {
    expect(bash(`find "${CKPT17}" -name "*.obj" -delete`)).toBe(REASONS.source)
    expect(bash(`find "${CKPT17}" -name "*.obj" -exec rm {} \\;`)).toBe(REASONS.source)
  })
  test('allows listing, finding and copying out of the export folder', () => {
    expect(bash('ls "D:/PROJECTS/UC ENVIRONMENT BUILDING/REQUIREMENTS"')).toBeUndefined()
    expect(bash(`find "${CKPT17}" -name "*.obj"`)).toBeUndefined()
    expect(bash('cp "D:/PROJECTS/UC ENVIRONMENT BUILDING/x.obj" data/snap/')).toBeUndefined()
    expect(bash(`"$PY" -m engine.cli freeze --export "${CKPT17}"`)).toBeUndefined()
  })
})

describe('rule 2: no bare cd', () => {
  test('denies cd at the start of a Bash command', () => {
    expect(bash(`cd "${WT}" && git status`)).toBe(REASONS.cdBash)
  })
  test('denies cd later in a top-level chain, after shell keywords, and via builtin', () => {
    expect(bash('git status && cd /tmp')).toBe(REASONS.cdBash)
    expect(bash('if [ -d x ]; then cd x; fi')).toBe(REASONS.cdBash)
    expect(bash('builtin cd /d/x')).toBe(REASONS.cdBash)
  })
  test('a here-string does not hide the lines after it', () => {
    expect(bash('grep a <<<"text"\ncd /d/x')).toBe(REASONS.cdBash)
  })
  test('denies Set-Location in PowerShell, even in parentheses', () => {
    expect(ps('Set-Location "D:\\x"; git status')).toBe(REASONS.cdPs)
    expect(ps('( Set-Location D:/x ); git status')).toBe(REASONS.cdPs)
  })
  test('allows cd inside a subshell, git -C, heredoc text and quoted text', () => {
    expect(bash(`( cd "${WT}" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q )`)).toBeUndefined()
    expect(bash(`git -C "${WT}" status`)).toBeUndefined()
    expect(bash("cat > notes.md <<'EOF'\ncd somewhere\nEOF")).toBeUndefined()
    expect(bash('echo "cd x"')).toBeUndefined()
  })
})

describe('rule 3: shared working tree git', () => {
  test('denies blanket staging, commit -a, bare stash and force push', () => {
    for (const c of [
      'git add -A',
      `git -C "${ROOT}" add .`,
      'git add --all',
      'git commit -a -m x',
      'git commit -am "x"',
      'git stash',
      'git stash push',
      'git push --force origin x',
      'git push -f',
      'git push origin +main',
      'if true; then git add -A; fi',
    ]) expect(bash(c)).toBe(REASONS.git)
    expect(ps('git add .\\')).toBe(REASONS.git)
  })
  test('allows staging by name, messages that mention flags, stash push -m, plain push', () => {
    for (const c of [
      'git add engine/decide/jev.py',
      'git commit -m "never git add -A"',
      'git stash push -m "wip: mine"',
      'git stash list',
      'git push origin claude/M1',
      'git push -u origin claude/M1',
      `git -C "${ROOT}" add engine/a.py`,
    ]) expect(bash(c)).toBeUndefined()
  })
})

describe('rule 4: live containers and database', () => {
  test('denies restarting fixer containers, compose up/down and psql on fixer', () => {
    for (const c of [
      'docker restart fixer-api',
      'docker container restart fixer-web',
      'docker compose up -d',
      'docker-compose down',
      'docker stop fixer-db',
      'docker exec fixer-db psql -U postgres -d fixer -c "select 1"',
      'docker exec fixer-db psql -U fixer fixer',
      'psql postgresql://u@localhost:5490/fixer',
    ]) expect(bash(c)).toBe(REASONS.live)
  })
  test('compose global options do not hide the subcommand (review finding 1, HANDOFF.md:351)', () => {
    for (const c of [
      'docker compose -p ucmodelfixer up -d --no-build api web',
      'docker compose -f docker-compose.yml up -d',
      'docker compose -p ucmodelfixer restart api',
    ]) expect(bash(c)).toBe(REASONS.live)
  })
  test('allows reading container state, test databases, and the fixer role (review finding 3)', () => {
    for (const c of [
      'docker ps',
      'docker logs fixer-api',
      'docker compose -p ucmodelfixer logs api',
      'docker exec fixer-db psql -U postgres -d fixer_test_123_a -c "select 1"',
      'docker exec fixer-db psql -U fixer -d fixer_test_123_a -c "select 1"',
      'docker exec fixer-db psql -U fixer -l',
      'docker restart some-other-thing',
    ]) expect(bash(c)).toBeUndefined()
  })
})

describe('rule 5: secret files', () => {
  test('denies reading .env, .env.local, .env*, auth.json and the phone-session config', () => {
    expect(check('Read', { file_path: `${ROOT}\\.env` })).toBe(REASONS.secret)
    expect(check('Read', { file_path: '.env.local' })).toBe(REASONS.secret)
    expect(check('Read', { file_path: `${ROOT}/api/.env.production` })).toBe(REASONS.secret)
    expect(check('Edit', { file_path: `${ROOT}/.env`, old_string: 'a', new_string: 'b' })).toBe(REASONS.secret)
    expect(check('Grep', { pattern: 'KEY', path: `${ROOT}/.env` })).toBe(REASONS.secret)
    expect(check('Grep', { pattern: 'KEY', glob: '.env*' })).toBe(REASONS.secret)
    expect(bash('cat .env')).toBe(REASONS.secret)
    expect(bash('cat .env*')).toBe(REASONS.secret)
    expect(bash(`cat "${ROOT}/.env"`)).toBe(REASONS.secret)
    expect(ps('Get-Content .env')).toBe(REASONS.secret)
    expect(check('Read', { file_path: 'C:\\Users\\me\\.config\\gh\\auth.json' })).toBe(REASONS.secret)
    expect(bash('ls "D:/PROJECTS/Corllenium-Phone-session-Config"')).toBe(REASONS.secret)
    expect(bash(`python -c "print(open('.env').read())"`)).toBe(REASONS.secret)
    expect(check('Monitor', { command: 'tail -f .env' })).toBe(REASONS.secret)
  })
  test('allows .env.example, .venv, ordinary files and prose that mentions .env (review finding 5)', () => {
    expect(check('Read', { file_path: `${ROOT}/.env.example` })).toBeUndefined()
    expect(check('Read', { file_path: `${ROOT}/engine/decide/jev.py` })).toBeUndefined()
    expect(bash(`"${ROOT}/.venv/Scripts/python.exe" -m pytest`)).toBeUndefined()
    expect(bash('git commit -m "read the key from the .env fallback"')).toBeUndefined()
    expect(bash(`git commit -m "uc-guard: deny reading '.env'"`)).toBeUndefined()
    expect(bash("cat > t.ts <<'EOF2'\nconst f = '.env'\nopen('.env')\nEOF2")).toBeUndefined()
    expect(bash('grep -rn "\\.env" engine api')).toBeUndefined()
    expect(bash('git log --format=%B | grep -c Corllenium-Phone-session-Config')).toBeUndefined()
    expect(bash('echo $HOME && node -e "console.log(process.env.HOME)"')).toBeUndefined()
  })
})

describe('rule 6: the owner result folders take only verified output', () => {
  test('denies Write, copies, engine runs and find -delete into the result folders', () => {
    expect(check('Write', { file_path: `${ROOT}\\OBJ FIXED RESULT\\CHTM\\a.obj`, content: 'x' })).toBe(REASONS.results)
    expect(bash(`cp data/output/x.skp "${ROOT}/MODEL FIXER ENGINE FILES/05-FIXING/CHTM/"`)).toBe(REASONS.results)
    expect(bash('"$PY" -m engine.cli export --out "MODEL FIXER ENGINE FILES/04-COLORING"')).toBe(REASONS.results)
    expect(bash(`find "${ROOT}/OBJ FIXED RESULT" -name "*.obj" -delete`)).toBe(REASONS.results)
  })
  test('naming the verified folder elsewhere in the command does not exempt a copy', () => {
    expect(bash(`ls .claude/worktrees/verified; cp data/out/a.obj "${ROOT}/OBJ FIXED RESULT/"`)).toBe(REASONS.results)
    expect(bash(`( cd "${ROOT}/.claude/worktrees/verified-old" && cp a.obj "${ROOT}/OBJ FIXED RESULT/" )`)).toBe(REASONS.results)
  })
  test('allows publishing from the verified worktree, listing, and prose (review finding 4)', () => {
    expect(bash(`( cd "${VERIFIED}" && "$PY" -m engine.cli export --out "${ROOT}/MODEL FIXER ENGINE FILES/04-COLORING" )`)).toBeUndefined()
    expect(bash(`cp "${VERIFIED}/data/output/a.obj" "${ROOT}/OBJ FIXED RESULT/CHTM/"`)).toBeUndefined()
    expect(bash(`ls "${ROOT}/OBJ FIXED RESULT"`)).toBeUndefined()
    expect(check('Read', { file_path: `${ROOT}/OBJ FIXED RESULT/CHTM/a.obj` })).toBeUndefined()
    expect(bash('git commit -m "docs: refresh OBJ FIXED RESULT from verified"')).toBeUndefined()
    expect(bash('echo "- published OBJ FIXED RESULT" >> .superpowers/sdd/x/progress.md')).toBeUndefined()
    expect(bash('git log --oneline -- "OBJ FIXED RESULT"')).toBeUndefined()
  })
})

describe('through the engine', () => {
  test('a denied call ends with the rule as its reason, and the tool never runs', async ($, on) => {
    let ran = false
    on('tool.call', () => { ran = true; return { result: 'ran' } as never })
    const r = await $.tool.call({ tool: 'Bash', command: 'git add -A' })
    expect(ran).toBe(false)
    // the kit hands a plugin-raised call its { deny }; a session's model sees it as an errored result
    expect(r.deny ?? (r.isError ? r.text : undefined) ?? '').toBe(`uc-guard: ${REASONS.git}`)
  })
  test('an allowed call reaches the tool unchanged', async ($, on) => {
    let seen = ''
    on('tool.call', (_$, e) => { seen = e.tool === 'Bash' ? e.command : ''; return { result: 'ran' } as never })
    await $.tool.call({ tool: 'Bash', command: 'git status' })
    expect(seen).toBe('git status')
  })
})
