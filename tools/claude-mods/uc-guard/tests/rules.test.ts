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
  test('psql -d and --dbname values in URI or conninfo form name the live database (re-review 1)', () => {
    for (const c of [
      'psql -d "postgresql://fixer:fixer@localhost:5490/fixer" -c "delete from x"',
      'psql --dbname=postgresql://fixer:fixer@localhost:5490/fixer',
      'psql -d "host=localhost dbname=fixer"',
    ]) expect(bash(c)).toBe(REASONS.live)
    expect(bash('psql -d "postgresql://fixer:fixer@localhost:5490/fixer_test_1_a" -c "select 1"')).toBeUndefined()
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
    expect(bash('cat \\.env')).toBe(REASONS.secret)
  })
  test('the engine may be handed the key file: python -m engine.cli ... --env-file (M1b)', () => {
    expect(bash(`"$PY" -m engine.cli decide-pilot --env-file "${ROOT}/.env" --out data/campus/jev_pilot.json`)).toBeUndefined()
    expect(bash(`( cd "${WT}" && PYTHONPATH="$PWD" "$PY" -m engine.cli decide-pilot --env-file="${ROOT}/.env" )`)).toBeUndefined()
    expect(bash(`"$PY" -m engine.cli decide-pilot --source "${ROOT}/.env"`)).toBe(REASONS.secret)
    expect(bash(`"$PY" -m other.tool --env-file "${ROOT}/.env"`)).toBe(REASONS.secret)
    expect(bash(`"$PY" -m engine.cli decide-pilot --env-file "${ROOT}/.env"; cat "${ROOT}/.env"`)).toBe(REASONS.secret)
  })
  test('only a Python interpreter running -m engine.cli as its module gets the exemption (M1b review)', () => {
    expect(bash(`"$PY" -u -m engine.cli decide-pilot --env-file "${ROOT}/.env"`)).toBeUndefined()
    expect(ps(`& "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m engine.cli decide-pilot --env-file "${ROOT}/.env"`)).toBeUndefined()
    for (const c of [
      `docker run --rm --env-file "${ROOT}/.env" alpine sh -c env -m engine.cli`,
      `"$PY" dump.py --env-file "${ROOT}/.env" -m engine.cli`,
      `"$PY" -c "import sys; print(open(sys.argv[2]).read())" --env-file "${ROOT}/.env" -m engine.cli`,
      `"$PY" -c"import sys; print(open(sys.argv[4]).read())" -m engine.cli --env-file "${ROOT}/.env"`,
      `"$PY" - -m engine.cli --env-file "${ROOT}/.env" < dump.py`,
      `"$PY" - -m engine.cli --env-file "${ROOT}/.env" <<'EOF'\nprint(open(__import__('sys').argv[4]).read())\nEOF`,
      `"$PY" -X dev -m engine.cli --env-file "${ROOT}/.env"`,
    ]) expect(bash(c)).toBe(REASONS.secret)
    expect(bash(`py -3.12 -B -m engine.cli decide-pilot --env-file "${ROOT}/.env"`)).toBeUndefined()
  })
  test('allows .env.example, .venv, ordinary files and prose that mentions .env (review finding 5)', () => {
    expect(check('Read', { file_path: `${ROOT}/.env.example` })).toBeUndefined()
    expect(check('Read', { file_path: `${ROOT}/engine/decide/jev.py` })).toBeUndefined()
    expect(bash(`"${ROOT}/.venv/Scripts/python.exe" -m pytest`)).toBeUndefined()
    expect(bash('git commit -m "read the key from the .env fallback"')).toBeUndefined()
    expect(bash(`git commit -m "uc-guard: deny reading '.env'"`)).toBeUndefined()
    expect(bash("cat > t.ts <<'EOF2'\nconst f = '.env'\nopen('.env')\nEOF2")).toBeUndefined()
    expect(bash('grep -rn "\\.env" engine api')).toBeUndefined()
    expect(bash("git grep -n '\\.env' api")).toBeUndefined()
    expect(bash("git log -G '\\.env' --oneline")).toBeUndefined()
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
    expect(bash(`( cd "${VERIFIED}" && ls ); cp data/x.obj "${ROOT}/OBJ FIXED RESULT/"`)).toBe(REASONS.results)
    expect(bash(`( cd "${VERIFIED}" && ls ); ( cp data/x.obj "${ROOT}/OBJ FIXED RESULT/" )`)).toBe(REASONS.results)
  })
  test('rsync -t keeps times, it names no target (re-review round 2)', () => {
    expect(bash('rsync -t a.obj "/d/PROJECTS/UC ENVIRONMENT BUILDING/x/"')).toBe(REASONS.source)
  })
  test('cp -t / mv -t and --out= into the result folders are writes (re-review 2)', () => {
    expect(bash(`cp -t "${ROOT}/OBJ FIXED RESULT/CHTM" data/output/a.obj`)).toBe(REASONS.results)
    expect(bash(`mv -t "${ROOT}/MODEL FIXER ENGINE FILES/05-FIXING" a.skp`)).toBe(REASONS.results)
    expect(bash('"$PY" -m engine.cli export --out="OBJ FIXED RESULT"')).toBe(REASONS.results)
    expect(bash(`cp -t "D:/PROJECTS/UC ENVIRONMENT BUILDING/x" a.obj`)).toBe(REASONS.source)
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

describe('rule 7: stop only your own processes, by PID (M1c)', () => {
  test('denies killing by image name in Bash and cmd forms', () => {
    for (const c of [
      'taskkill /F /T /IM python.exe',
      'taskkill /im node.exe /f',
      'taskkill -IM python.exe -F',
      'taskkill /F /FI "IMAGENAME eq python.exe"',
      'pkill -f uvicorn',
      'killall python3',
      'wmic process where name="python.exe" delete',
      'wmic process where "name=\'python.exe\'" call terminate',
    ]) expect(bash(c)).toBe(REASONS.kill)
  })
  test('denies killing by name in PowerShell', () => {
    for (const c of [
      'Stop-Process -Name python -Force',
      'spps -n node',
      'Stop-Process -ProcessName python',
      'Get-Process python | Stop-Process -Force',
      "Get-Process | Where-Object { $_.Name -eq 'python' } | Stop-Process",
      'gps node | kill',
    ]) expect(ps(c)).toBe(REASONS.kill)
  })
  test('review round 1: Git Bash //IM, any /FI, by-name selection stopped by id or .Kill()', () => {
    for (const c of [
      'taskkill //F //T //IM python.exe',
      'taskkill //FI "IMAGENAME eq python.exe" //F',
      'taskkill /F /FI "PID gt 1000"',
      'taskkill /F /FI "MEMUSAGE gt 100000"',
      'taskkill /F /FI "STATUS eq RUNNING" /FI "IMAGENAME eq python.exe"',
    ]) expect(bash(c)).toBe(REASONS.kill)
    for (const c of [
      'Get-Process python | ForEach-Object { Stop-Process -Id $_.Id -Force }',
      '(Get-Process python).Kill()',
      'Get-Process -Name python | ForEach-Object { $_.Kill() }',
    ]) expect(ps(c)).toBe(REASONS.kill)
  })
  test('review round 1 minors: nested cmd/powershell, env/timeout wrappers, kill -1, pgrep with kill', () => {
    for (const c of [
      'cmd /c taskkill /F /IM python.exe',
      'powershell -c "Stop-Process -Name python"',
      'pwsh -Command "Get-Process python | Stop-Process"',
      'env -i pkill python',
      'timeout 5 pkill python',
      'kill -9 -1',
      'pgrep -f python | xargs kill -9',
      'kill $(pgrep -f python)',
    ]) expect(bash(c)).toBe(REASONS.kill)
    expect(ps('cmd /c taskkill /F /IM python.exe')).toBe(REASONS.kill)
  })
  test('separate statements do not pair: listing then stopping something else by id passes', () => {
    expect(ps('Get-Process | Out-Null; $p | Stop-Process')).toBeUndefined()
    expect(ps('Get-Process python\nStop-Process -Id 5')).toBeUndefined()
    expect(bash('taskkill //PID 1234 //F')).toBeUndefined()
    expect(bash('pgrep -f python')).toBeUndefined()
  })
  test('allows stopping one process by its id, and listing processes', () => {
    expect(bash('taskkill /PID 1234 /T /F')).toBeUndefined()
    expect(bash('kill 1234')).toBeUndefined()
    expect(bash('kill -9 1234 5678')).toBeUndefined()
    expect(bash('ps aux | grep python')).toBeUndefined()
    expect(bash('tasklist /FI "IMAGENAME eq python.exe"')).toBeUndefined()
    expect(ps('Stop-Process -Id 1234 -Force')).toBeUndefined()
    expect(ps('Get-Process -Id 1234 | Stop-Process')).toBeUndefined()
    expect(ps('Get-Process python | Select-Object Id, CPU')).toBeUndefined()
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
