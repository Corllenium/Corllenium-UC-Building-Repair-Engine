# J5 report: image, VPS stack files, runbook

Status: DONE_WITH_CONCERNS. Worktree `.claude/worktrees/J5`, branch `claude/J5`, base 8a2cd44.

## Commits
- `49d860e` feat(decide-service): main (module `app` only when DECIDE_DATABASE_URL is set; decider reads key from env only) + `tests/test_main.py`
- `ddc3c2f` feat(decide-service): image, VPS compose service, nginx route, runbook (Jev off by default): Dockerfile, requirements.txt, docker-compose.yml, nginx.conf, README.md

## Tests (test-first)
`deploy/vps/decide/tests/test_main.py`, 6 tests:
- import without DB URL builds no `app`;
- import with DB URL builds `app`, calls `PostgresStore(url)` then `ensure_schema()` once;
- `build_app(store_factory=MemoryStore)` health says `jev_enabled: false`;
- `make_decider().available` follows a fake TYPESAFE_API_KEY set/unset;
- `repr`/`str` never show the key;
- the decider's env file is `/nonexistent`.

Red: first run, 7 failed (module `decide_service.main` absent; the earlier draft had 7 tests). Green after `main.py`.
One test was fixed in my own test (it set DECIDE_DATABASE_URL before importing main, so the module-level app tried a real
Postgres); import first, then set the env.
Area suite: `149 passed, 113 skipped` (the 113 are the Postgres-parametrised tests, skipped without DECIDE_TEST_DATABASE_URL; they were not run here).

Design note: `ensure_schema()` is called inside the default store factory (`_postgres_store`), because MemoryStore has none.

## Docker build tail
```
#12 [8/8] COPY deploy/vps/decide/schema.sql /app/schema.sql
#13 exporting manifest list sha256:841dcb56...
#13 naming to docker.io/library/ucmodelfixer-decide:vps done
#13 DONE 5.2s
```
In the image: `import typesafe_sdk, fastapi, psycopg` OK (fastapi 0.142.4).

## Smoke run 1: decide container directly (network decide-smoke, db decide-smoke-db, decide-smoke, host port 58200)
```
--- health gab
{"ok":true,"jev_enabled":false,"tokens_today":0,"daily_token_cap":1000000,"model":"jev-latest"}
HTTP 200
--- health no header
{"detail":"no user"}
HTTP 401
--- ask uc-engine (one Choice question)
{"answers":{"material":{"answer":null,"confidence":0.0,"probabilities":{},"source":"none","accepted":false,"error":"jev off","suggestion_id":null}}}
HTTP 200
--- ask gab
{"detail":"engine only"}
HTTP 403
```

## Smoke run 2: real deploy/vps/nginx.conf in front (extra throwaway `decide-smoke-web`, nginx:alpine; decide container given the aliases uc-fixer-decide and uc-fixer-api; test logins in a scratchpad htpasswd, throwaway passwords)
```
health as gab (login)                 -> {"ok":true,"jev_enabled":false,...} HTTP 200
health, no login                      -> HTTP 401
ask as gab, client sent X-Remote-User: uc-engine -> nginx 403 Forbidden (spoof does not work)
ask as uc-engine                      -> {"answers":{"m":{... "source":"none","error":"jev off" ...}}} HTTP 200
suggestions as gab, client sent X-Remote-User: nobody -> HTTP 200 (nginx replaced the header)
suggestions as uc-engine, client sent X-Remote-User: gab -> {"detail":"owner only"} HTTP 403
```
All throwaway containers and the network were stopped/removed; `docker ps -a` and `docker network ls` show no `decide-smoke*`. fixer-api, fixer-web, fixer-db untouched and still running. No docker compose was run.

## Acceptance checks
- docker-compose.yml: service `decide` has no `ports` key (grep: none).
- nginx.conf: `proxy_set_header X-Remote-User $remote_user;` appears in both decide locations (count 2).

## Concerns
1. **Brief bug fixed:** the brief put `DECIDE_JEV_ENABLED: "false"` under `environment` AND said to switch Jev on by adding the line to `decide.env`. In Compose `environment` overrides `env_file`, so the switch would silently do nothing. I left `DECIDE_JEV_ENABLED` out of `environment` (the service default is false; a comment in the compose file says why). Not verified with compose (no compose allowed); this is documented Compose precedence.
2. `decide.env` must exist before `docker compose up -d decide` (compose errors on a missing env_file). The runbook orders it so (step 2). Not tested on the VPS.
3. The owner's PowerShell commands (htpasswd for uc-engine, decide.env writer) were not run on the VPS. The decide.env shell logic was run locally with a fake key through bash (writes `TYPESAFE_API_KEY=<value>`). The PowerShell quoting (backtick-escaped `$K`, no inner double quotes) is untested in PowerShell itself.
4. Runbook uses `docker save -o` + `scp` instead of `docker save | ssh`, because the PowerShell pipeline corrupts binary streams (a deviation from the brief, deliberate).
5. nginx resolves `uc-fixer-decide` at load/reload; reload fails if the container does not exist. The runbook orders compose-up before the nginx reload and says to reload after a recreate.
6. The Postgres-parametrised tests (113) were skipped; the real PostgresStore was exercised only via the container smoke runs (health and ask with Jev off; `ask` with Jev off writes nothing, so the write path was not exercised).
7. The `/api/decide/ask` exact-match location omits `Host` / `X-Real-IP` headers (as in the brief); harmless.

---
# Fix round 1 (review: CHANGES)

Commits: `8d7d863` (nginx: items 1, 3), `ec882ca` (README for item 1), `c173641` (Dockerfile + requirements: items 2, 7), `27cb477` (README: items 4, 5, 6). Item 8 is a test run, no commit.

## 1. Per-request upstream resolution (nginx.conf)
`resolver 127.0.0.11 valid=10s ipv6=off;` at server level; both decide locations use `set $decide_up http://uc-fixer-decide:8200; proxy_pass $decide_up;` (no URI part). Runbook: the reload-after-recreate step is gone (one reload to load the new conf stays); rollback text says the locations answer 502 and removing them is optional but recommended.
Throwaway test (network decide-fix-net, nginx:alpine with the real nginx.conf, a stand-in container aliased uc-fixer-api so the old static `/api/` location resolves):
```
nginx started (no emerg) with NO uc-fixer-decide on the network
decide health (gab)                -> 502
decide ask (uc-engine)             -> 502
site / (gab)                       -> <html>site</html> 200
no login                           -> 401
error log: "uc-fixer-decide could not be resolved (3: Host not found)"  (per request, not a startup failure)
--- decide container (alias uc-fixer-decide) joins, NO nginx reload, ~14 s later:
decide health (gab)                -> {"ok":true,"jev_enabled":false,...} 200
ask as uc-engine                   -> {"answers":{"m":{...,"source":"none","error":"jev off",...}}} 200
suggestions as gab, client header X-Remote-User: nobody -> 200 (header replaced)
```
Test caveat: my stand-in for uc-fixer-api exited, so the old `/api/` location (static upstream, unchanged and out of scope) gave 502; not related to this change.

## 3. `location ^~ /api/decide/ask` prefix
Keeps `if ($remote_user != "uc-engine") { return 403; }`; now also sets Host, X-Real-IP, X-Remote-User and proxy_read_timeout. Verified as gab (POST): `/api/decide/ask` 403, `/api/decide/ask/` 403, `/api/decide/ask%3F` 403 (both with the upstream absent and present).

## 2. Non-root
Dockerfile: `RUN useradd --system --no-create-home decide` and `USER decide` before CMD. Rebuilt.
```
$ docker run --rm --entrypoint id ucmodelfixer-decide:vps
uid=999(decide) gid=999(decide) groups=999(decide)
```
The rebuilt image started against a throwaway Postgres and answered health 200 with `jev_enabled` false (then removed).

## 7. Pins (from `pip freeze` of the image)
`fastapi==0.142.4`, `uvicorn[standard]==0.54.0`, `psycopg[binary]==3.3.6`, `typesafe-sdk==0.7.2`, `pydantic==2.13.5`. The rebuilt image's freeze shows these same versions.

## 4, 5, 6. README
- Key command now `... echo; set -f; IFS=; printf 'TYPESAFE_API_KEY=%s\n' `$K > ...`; tested locally in bash with a fake key `FAKE*ab  c?` (kept intact). A bullet states root's login shell must be bash, with the check `getent passwd root` (must end in `/bin/bash`).
- Warning that re-running step 2 rewrites decide.env and drops `DECIDE_JEV_ENABLED=true`; the rotate-while-on procedure is given.
- Line added: "The controller runs steps 3-5 only with the owner's explicit OK at that moment."
Not run in PowerShell itself (quoting unverified there).

## 8. Whole service suite against Postgres
Throwaway `decide-test-pg` (postgres:16-alpine, `--rm`, port 55432), DECIDE_TEST_DATABASE_URL set:
```
262 passed, 1 warning in 20.41s
```
Container stopped and gone afterwards. All `decide-fix-*` containers and the network removed. No compose, no fixer-* touched.
