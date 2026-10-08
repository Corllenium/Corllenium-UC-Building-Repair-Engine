# Final fix wave, feat/jev-vps (branch claude/jev-final, base 16355b9)

Status: DONE_WITH_CONCERNS. Commits, oldest first:

| Commit | Group | Items |
|---|---|---|
| a79736b | nginx | 1 |
| 81218e3 | service | 2, 4 (service side) |
| 0e09414 | web | 3, 4 (client side), 5 |
| 91a9fa7 | runbook | 6, 7, 8, 9 |
| e463ee7 | docs | 10, 11 |

All commits end with `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`. Nothing merged or pushed.

## Item 1: nginx (a79736b)
`if ($remote_user = "uc-engine") { return 403; }` is now the first line of `location /` and of `location /api/` in
`deploy/vps/nginx.conf` (the file keeps its CRLF working-copy endings). Probe: throwaway `nginx:alpine` containers
`final-fix-web` (the real nginx.conf, copied in with `docker cp`), `final-fix-api` and `final-fix-decide` (echo
upstreams with network aliases `uc-fixer-api` and `uc-fixer-decide`) on the network `final-fix-net`; htpasswd with
`uc-engine` and `gab`, both fake passwords (apr1). `nginx -t` said ok. All containers and the network were removed
afterwards (`docker ps -a | grep final-fix` is empty).

```
uc-engine GET /                      -> 403 Forbidden
uc-engine GET /jev                   -> 403 Forbidden
uc-engine GET /api/models            -> 403 Forbidden
uc-engine GET /api/decide/health     -> 200 UPSTREAM decide GET /api/decide/health remote_user=uc-engine
uc-engine POST /api/decide/ask       -> 200 UPSTREAM decide POST /api/decide/ask remote_user=uc-engine
gab GET /                            -> 200 <html>web index</html>
gab GET /api/models                  -> 200 UPSTREAM api GET /api/models
gab POST /api/decide/ask             -> 403 Forbidden
gab POST /api/models (read only)     -> 403 Forbidden
gab GET /api/decide/health           -> 200 UPSTREAM decide GET /api/decide/health remote_user=gab
gab GET /api/decide/suggestions      -> 200 UPSTREAM decide GET /api/decide/suggestions remote_user=gab
no login GET /                       -> 401 Authorization Required
no login GET /api/decide/health      -> 401 Authorization Required
```
(`gab POST /api/decide/ask` was probed twice in the script, same 403 both times.)

## Item 2: accepted only for owner answers (81218e3)
Tests (deploy/vps/decide/tests/test_logic.py): the J2 test `test_accepted_follows_the_service_min_confidence_fresh_and_cached`
asserted confidence-based `accepted`; it is replaced by `test_accepted_is_never_set_by_confidence_fresh_or_cached`
(this is the final review's ruling; the commit message says so). New: `test_a_099_confidence_jev_answer_is_not_accepted`,
`test_pilot_import_answer_is_not_accepted_and_keeps_its_confidence`, `test_only_the_owners_answer_is_accepted`.
`FakeClient`/`_setup` got a `confidence` parameter (default 0.95, so existing tests are unchanged).

Red (before the change): `4 failed, 149 passed, 114 skipped`. The three accepted tests failed, e.g.
`assert ('pilot-import' == 'pilot-import' and 0.97 == 0.97 and True is False)`.
Green (after item 4 as well): `153 passed, 114 skipped`.

`logic.py`: cached non-owner rows use `accepted=False`; fresh Jev answers use `dataclasses.replace(d, accepted=False)`;
owner answers stay `True`. Confidence is returned unchanged. RemoteDecider needed no change: `wire.decision_from_json`
passes the flag through (`accepted is True` only), already covered by `test_accepted_is_true_only_for_the_json_true`.
`cfg.min_confidence` is still a setting (display threshold) but no longer used by `logic.py`.

## Item 4: reask needs a JSON body (81218e3 service, 0e09414 client)
Service: `ReaskBody(BaseModel)` (empty model) on `POST /api/decide/reask/{id}`. Test
`test_reask_needs_a_json_body_a_form_or_empty_post_is_422`: no body, a form post and a `text/plain` post each get 422
and Jev is never called; `json={}` gets 200. The existing reask tests now send `json={}` (8 call sites). The
role tests still pass without a body (a 401/403 comes before body validation).
Red: the new test failed with `assert 200 == 422` (the empty post was accepted). Green: as above.
Client: `reaskSuggestion` sends header `Content-Type: application/json` and body `'{}'`; test
`reaskSuggestion sends a JSON body {}` (red: it sent no body; green below).

## Items 3 and 5: web (0e09414)
- `jevReview.ts` TABS: Review order `['review.priority']`; Fix tie-breaks `['e5.winner', 'e4.same_look', 'e8.opening_kind']`;
  Next repair step stays `['repair.next_step']`. Test: `keeps the reserved qtypes of the three tabs that are not live yet`.
- `isServiceMissing` is true for a 404 only; new `isServiceUnreachable` (502 only) and `serviceNote(err)`:
  502 gives "Jev service unreachable", 404 gives "Jev service runs on the VPS", anything else null. `JevView.vue`
  shows the note through one `serviceBanner` ref (both the load and the health paths). Systemic handling in
  `runAcceptAll` is unchanged (a service 404 or 502 still stops the loop).
Red: `5 failed, 39 passed (44)` over jevReview.test.ts and decide.test.ts (reserved qtypes, the 404-only case,
`isServiceUnreachable is not a function`, `serviceNote is not a function`, reask body).
Green: full web suite `Test Files 18 passed (18), Tests 151 passed (151)`.
Not done: no `vue-tsc` type check and no browser look at the changed banner (the worktree has no node_modules and
`npm install` is forbidden); the template change is one `v-if` on a string ref.

## Items 6-9: runbook `deploy/vps/README.md` (91a9fa7)
- Step 3 (new, before the decide image): build `ucmodelfixer-web:vps` on the PC (owner's OK), `docker save -o`, `scp`,
  `docker load`; the decide steps are renumbered 4-6; step 5 is `docker compose up -d --force-recreate web` (which
  loads the new nginx.conf, replacing the old `nginx -s reload`) and then `docker compose up -d decide`.
- New "On the PC after the deploy": `UC_DECIDE_URL=https://uc-fixer.srv1866850.hstgr.cloud`, the owner adds
  `UC_DECIDE_PASSWORD=<uc-engine password>` to the repo-root `.env` himself, `decide-import-pilot --source --materials --pilot`
  (first `--dry-run`), then `decide-pull --type mat.category`. The flags were checked against `engine/cli.py`.
- New "Post-deploy checks (spec section 8)": health; one ask as uc-engine; one review as the owner in `/jev`; one
  confirmed fetch; one refusal per role (uc-engine on `/` 403, uc-engine on review 403, owner on ask 403).
- The "0.8 gates what is accepted" sentence is replaced by the display-threshold wording from the brief.

## Items 10-11: plan and spec (e463ee7)
Plan: schema (`question json`, `state_json jsonb not null`), `Json` for `question` and `Jsonb` for the rest,
compose `environment` without `DECIDE_JEV_ENABLED` (reason given), nginx block (`^~ /api/decide/ask`, resolver,
variable upstream, uc-engine 403 on `/` and `/api/`), Dockerfile with non-root user, pinned requirements, decide.env
command (`set -f; IFS=; chmod 600`, bash check), `save -o` + scp, `--force-recreate` for switching on, the texture
file name as text with no thumbnail. Spec: sections 3, 4 (table, order step 2, endpoints, a new `accepted` paragraph),
5, 6, 8 and 9 step 5 as listed in the brief.

## Suites
- Service, in-memory: `153 passed, 114 skipped, 1 warning` (the 114 are the Postgres halves).
- Service, Postgres pass on throwaway `decide-test-pg` (`docker run --rm -d -p 55432:5432 postgres:16-alpine`,
  DECIDE_TEST_DATABASE_URL on port 55432), run after the service commit, nothing in the service changed afterwards:
  `267 passed, 1 warning` (no skips). Container stopped (and removed by `--rm`).
- Engine decide tests (test_decide_wire, _jev, _pilot, _remote, _pilot_import): `119 passed`.
- Web (`vitest run --root <wt>/web --config j8-vite.config.mjs`): `Test Files 18 passed (18), Tests 151 passed (151)`.
- The binding-rule list of AGENTS.md sections 3-6 is not touched: no engine geometry, guard, FixProfile, live DB,
  container, export folder or CHECKPOINT-17 master was involved.

## Concerns, plainly
1. `Dockerfile.web` (and the root `nginx.conf` it copies) are untracked in the main checkout, so the new runbook
   step 3 builds from a file that is not in git. The step is written as the owner's own recipe; it would be better
   committed.
2. The plan's J8 bullet "on a fetch failure with status 404 or 502, 'Jev service runs on the VPS'" was changed to
   the new 404/502 split. It was not in the brief, but it contradicted item 5 otherwise.
3. Spec section 7 still says test databases are "in their own Docker project" (brief item 11 listed only section 8).
4. Deferred, as recorded in the brief: a cold ask of about 37 batches may exceed the 10 s client deadline and then
   fails safe as `none`; revisit when Jev is switched on (chunk on the client, or a longer timeout).
5. The nginx probe used echo upstreams, so it proves the routing and the 403s, not the real service behind it.

## Addendum: coordinator rulings on concerns 1 and 3 (docs only, no tests run)
Commit: see the last line of `git log` on claude/jev-final ("docs(vps,spec): web-image note ...").
- Concern 1: `deploy/vps/README.md`, web-image step 3, now has a note: `Dockerfile.web` and the root `nginx.conf` it
  copies are untracked in the main checkout (not in git); the build uses them as they exist on the owner's PC;
  committing them is a separate owner decision. Consistency check: `deploy/vps/docker-compose.yml` mounts
  `./nginx.conf` (relative to `/docker/uc-fixer` on the box) over `/etc/nginx/conf.d/default.conf`, and step 5 copies
  `deploy/vps/nginx.conf` there, so the box runs `deploy/vps/nginx.conf`, not the root one baked into the image. The
  untracked files were not touched or committed.
- Concern 3: spec §7 now says test databases are "in a throwaway container (`decide-test-pg`, `--rm`)".

## Addendum 2: two runbook fixes after the final re-review (docs only, commit 71cfa0e)
- Step 3 now builds with `npm --prefix web run build` (no `( cd web; ... )`, which PowerShell does not undo).
- Post-deploy check 2 is a real one-question POST to `/api/decide/ask` through `RemoteDecider` (not `decide-import-pilot`,
  which calls `/import`). The password comes from `UC_DECIDE_PASSWORD` or the repo-root `.env`, else a `getpass`
  prompt, so it is never on the command line. Expected with Jev off: `source none error 'jev off'`. I ran the same
  one-liner on this machine against an unreachable `http://localhost:9` with a fake password: output
  `source none error 'URLError'` (the command works; the VPS result itself is unverified until deploy). The `getpass`
  prompt branch was not exercised (no tty here).
