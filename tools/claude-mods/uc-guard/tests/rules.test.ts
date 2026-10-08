import { describe, expect, test } from 'claude-code/testing'
import { check } from '../hooks/rules.ts'

const ROOT = 'D:/PROJECTS/UC MODEL FIXER'
const WT = `${ROOT}/.claude/worktrees/P0-17`
const VERIFIED = `${ROOT}/.claude/worktrees/verified`

const bash = (command: string) => check('Bash', { command })
const ps = (command: string) => check('PowerShell', { command })

describe('rule 1: CHECKPOINT-17 export, master and backup are never written', () => {
  test('denies rm under the live export folder', () => {
    expect(bash('rm -rf "/d/PROJECTS/UC ENVIRONMENT BUILDING/REQUIREMENTS/01-MODEL-EXPORT/CKPT17/x.obj"')).toMatch(/AGENTS\.md §3/)
  })
  test('denies Write into the master folder', () => {
    expect(check('Write', { file_path: 'D:\\PROJECTS\\UC\\02-SKETCHUP\\current\\a.skp', content: 'x' })).toMatch(/master/)
  })
  test('denies Remove-Item in the backup folder', () => {
    expect(ps(`Remove-Item "D:\\PROJECTS\\UC MODEL FIXER\\MODEL FIXER ENGINE FILES\\02-SKETCHUP-MODELS\\CHECKPOINT-17-BACKUP\\x.skp"`)).toBeDefined()
  })
  test('denies cp with the export folder as destination', () => {
    expect(bash('cp a.obj "D:/PROJECTS/UC ENVIRONMENT BUILDING/x.obj"')).toBeDefined()
  })
  test('denies a redirect into the master folder', () => {
    expect(bash('echo x > "/d/PROJECTS/UC/02-SKETCHUP/current/note.txt"')).toBeDefined()
  })
  test('allows listing and copying out of the export folder', () => {
    expect(bash('ls "D:/PROJECTS/UC ENVIRONMENT BUILDING/REQUIREMENTS"')).toBeUndefined()
    expect(bash('cp "D:/PROJECTS/UC ENVIRONMENT BUILDING/x.obj" data/snap/')).toBeUndefined()
    expect(bash('"$PY" -m engine.cli freeze --export "D:/PROJECTS/UC ENVIRONMENT BUILDING/REQUIREMENTS/01-MODEL-EXPORT/CKPT17"')).toBeUndefined()
  })
})

describe('rule 2: no bare cd', () => {
  test('denies cd at the start of a Bash command', () => {
    expect(bash(`cd "${WT}" && git status`)).toMatch(/§8/)
  })
  test('denies cd later in a top-level chain', () => {
    expect(bash('git status && cd /tmp')).toBeDefined()
  })
  test('denies Set-Location in PowerShell', () => {
    expect(ps('Set-Location "D:\\x"; git status')).toBeDefined()
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
    ]) expect(bash(c)).toMatch(/Shared working tree/)
  })
  test('allows staging by name, messages that mention flags, stash push -m, plain push', () => {
    for (const c of [
      'git add engine/decide/jev.py',
      'git commit -m "never git add -A"',
      'git stash push -m "wip: mine"',
      'git stash list',
      'git push origin claude/M1',
      `git -C "${ROOT}" add engine/a.py`,
    ]) expect(bash(c)).toBeUndefined()
  })
})

describe('rule 4: live containers and database', () => {
  test('denies restarting fixer containers, compose up/down and psql on fixer', () => {
    for (const c of [
      'docker restart fixer-api',
      'docker compose up -d',
      'docker-compose down',
      'docker stop fixer-db',
      'docker exec fixer-db psql -U postgres -d fixer -c "select 1"',
      'psql postgresql://u@localhost:5490/fixer',
    ]) expect(bash(c)).toMatch(/live/)
  })
  test('allows reading container state and test databases', () => {
    for (const c of [
      'docker ps',
      'docker logs fixer-api',
      'docker exec fixer-db psql -U postgres -d fixer_test_123_a -c "select 1"',
      'docker restart some-other-thing',
    ]) expect(bash(c)).toBeUndefined()
  })
})

describe('rule 5: secret files', () => {
  test('denies reading .env, .env.local, auth.json and the phone-session config', () => {
    expect(check('Read', { file_path: `${ROOT}\\.env` })).toMatch(/secret/)
    expect(check('Read', { file_path: '.env.local' })).toBeDefined()
    expect(check('Edit', { file_path: `${ROOT}/.env`, old_string: 'a', new_string: 'b' })).toBeDefined()
    expect(check('Grep', { pattern: 'KEY', path: `${ROOT}/.env` })).toBeDefined()
    expect(bash('cat .env')).toBeDefined()
    expect(bash(`cat "${ROOT}/.env"`)).toBeDefined()
    expect(ps('Get-Content .env')).toBeDefined()
    expect(check('Read', { file_path: 'C:\\Users\\me\\.config\\gh\\auth.json' })).toBeDefined()
    expect(bash('ls "D:/PROJECTS/Corllenium-Phone-session-Config"')).toBeDefined()
    expect(bash(`python -c "print(open('.env').read())"`)).toBeDefined()
  })
  test('allows .env.example, .venv, ordinary files and messages that mention .env', () => {
    expect(check('Read', { file_path: `${ROOT}/.env.example` })).toBeUndefined()
    expect(check('Read', { file_path: `${ROOT}/engine/decide/jev.py` })).toBeUndefined()
    expect(bash(`"${ROOT}/.venv/Scripts/python.exe" -m pytest`)).toBeUndefined()
    expect(bash('git commit -m "read the key from the .env fallback"')).toBeUndefined()
    expect(bash('echo $HOME && node -e "console.log(process.env.HOME)"')).toBeUndefined()
  })
})

describe('rule 6: the owner result folders take only verified output', () => {
  test('denies Write and copies into the result folders', () => {
    expect(check('Write', { file_path: `${ROOT}\\OBJ FIXED RESULT\\CHTM\\a.obj`, content: 'x' })).toMatch(/verified/)
    expect(bash(`cp data/output/x.skp "${ROOT}/MODEL FIXER ENGINE FILES/05-FIXING/CHTM/"`)).toBeDefined()
    expect(bash('"$PY" -m engine.cli export --out "MODEL FIXER ENGINE FILES/04-COLORING"')).toBeDefined()
  })
  test('allows publishing from the verified worktree and listing', () => {
    expect(bash(`( cd "${VERIFIED}" && "$PY" -m engine.cli export --out "${ROOT}/MODEL FIXER ENGINE FILES/04-COLORING" )`)).toBeUndefined()
    expect(bash(`ls "${ROOT}/OBJ FIXED RESULT"`)).toBeUndefined()
    expect(check('Read', { file_path: `${ROOT}/OBJ FIXED RESULT/CHTM/a.obj` })).toBeUndefined()
  })
})

describe('through the engine', () => {
  test('a denied call ends errored with the reason, and the tool never runs', async ($, on) => {
    let ran = false
    on('tool.call', () => { ran = true; return { result: 'ran' } as never })
    const r = await $.tool.call({ tool: 'Bash', command: 'git add -A' })
    expect(ran).toBe(false)
    // the kit hands a plugin-raised call its { deny }; a session's model sees it as an errored result
    expect(r.deny ?? (r.isError ? r.text : undefined) ?? '').toMatch(/uc-guard: AGENTS\.md §3 "Shared working tree"/)
  })
  test('an allowed call reaches the tool unchanged', async ($, on) => {
    let seen = ''
    on('tool.call', (_$, e) => { seen = e.tool === 'Bash' ? e.command : ''; return { result: 'ran' } as never })
    await $.tool.call({ tool: 'Bash', command: 'git status' })
    expect(seen).toBe('git status')
  })
})
