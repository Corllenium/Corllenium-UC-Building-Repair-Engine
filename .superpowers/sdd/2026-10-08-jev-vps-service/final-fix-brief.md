# Final fix wave for feat/jev-vps (from the whole-branch review, 2026-10-08)

Worktree `.claude/worktrees/jev-final`, branch `claude/jev-final`, base 16355b9 (feat/jev-vps). One fixer does every item.
Test first wherever there is code. Commit per group.

## Code and config

1. **nginx (Important).** `uc-engine` must not pass nginx for anything but the decide routes.
   - In `deploy/vps/nginx.conf`, add `if ($remote_user = "uc-engine") { return 403; }` to `location /` and to
     `location /api/`.
   - Verify with a throwaway nginx:alpine named `final-fix-*` running the real nginx.conf:
     - with an htpasswd holding `uc-engine` and `gab`, both with fake passwords;
     - with echo upstreams aliased `uc-fixer-api` and `uc-fixer-decide`;
     - expected results:
       - `uc-engine` on `/`, `/jev` and `/api/models` gives 403;
       - `uc-engine` on `/api/decide/health` and on POST `/api/decide/ask` reaches the upstream;
       - `gab` on `/` and `/api/models` (GET) passes;
       - no login gives 401.
   - Paste the outputs and clean up. Never docker compose. Never touch fixer-*.
2. **Service `accepted` (ruling).** In `deploy/vps/decide/decide_service/logic.py`, every returned answer has
   `accepted = True` only when its source is `"owner"`. Cached, fresh Jev and pilot-import answers have
   `accepted = False`, and their `confidence` is still returned unchanged. Update the J2 tests that asserted
   confidence-based `accepted`: say in the commit message that this is the final review's ruling. Add a test that
   a 0.99-confidence Jev answer comes back `accepted False`. RemoteDecider passes the flag through unchanged.
3. **Reserved tab qtypes.** In `web/src/utils/jevReview.ts`, Review order is `review.priority`, and Fix tie-breaks is
   `e5.winner`, `e4.same_look` and `e8.opening_kind`. Next repair step stays `repair.next_step`. Update the tests.
4. **Re-ask needs a JSON body.** `POST /api/decide/reask/{id}` requires a JSON body; `{}` is enough. Use a pydantic
   model, so a form POST or an empty body gets 422 and blocks a cross-site trigger. The web client sends `{}`.
   Test both sides.
5. **A 502 means unreachable.** In `web/src/utils/jevReview.ts`, a 502 shows "Jev service unreachable", and only a 404
   shows "Jev service runs on the VPS". Test it.

## Runbook `deploy/vps/README.md`, the Jev section

6. **Web image step.** Add it before the decide container: build `ucmodelfixer-web:vps` on the PC (the owner's OK),
   `docker save -o`, scp, `docker load` on the box, then `docker compose up -d --force-recreate web`, which also
   loads the new nginx.conf.
7. **PC-side steps.**
   - Set `UC_DECIDE_URL=https://uc-fixer.srv1866850.hstgr.cloud`, and the owner adds the
     `UC_DECIDE_PASSWORD=<uc-engine password>` line to the repo-root `.env` himself.
   - Then run `"$PY" -m engine.cli decide-import-pilot --source … --materials … --pilot …` (first with `--dry-run`).
   - Then run `"$PY" -m engine.cli decide-pull --type mat.category`.
8. **Post-deploy checks (spec §8).** Health; one ask as uc-engine; one review as the owner in `/jev`; one confirmed
   fetch; and one refusal per role:
   - uc-engine on `/` gives 403;
   - uc-engine on review gives 403;
   - the owner on ask gives 403.
9. **README line ~85.** Replace the "0.8 gates what is accepted without review" wording with: 0.8 is only a
   display threshold for the confidence bar and the "Accept all ≥" default; nothing is used by the engine
   until the owner confirms it (`source` "owner", or the decide-pull files).

## Docs (the spec and plan in this branch)

10. **Plan** `docs/superpowers/plans/2026-10-08-jev-vps-service.md`:
    - ~L425: `question json` (not jsonb), and add `state_json jsonb not null`;
    - ~L454: `question` goes through `Json`, the rest through `Jsonb`;
    - ~L568: remove `DECIDE_JEV_ENABLED: "false"` from compose `environment`, with the reason;
    - ~L573-585: `^~ /api/decide/ask`, `resolver 127.0.0.11` and a variable upstream; plus the uc-engine 403 on `/`
      and `/api/`;
    - the Dockerfile: a non-root user and pinned requirements;
    - ~L591-595: the decide.env command with `set -f; IFS=; chmod 600` and the bash check; `save -o` + scp; switching
      on uses `--force-recreate`;
    - ~L722: the texture file name as text, no thumbnail (ruling).
11. **Spec** `docs/superpowers/specs/2026-10-08-jev-vps-service-design.md`:
    - §4 table: `key` replaces `state_hash`; define it as sha256 of state + kind + instructions + ordered criteria,
      with qtype and subject not in it; add `state_json`; `question` is json;
    - §4 order step 2: the lookup is by key;
    - §4 endpoints:
      - suggestions takes limit and offset and returns `{items, counts}`;
      - ask answers carry `suggestion_id`;
      - a bad review answer gets 422;
      - import returns `{added, skipped, invalid}`;
      - reask needs a JSON body, gets 409 when Jev is off or over the cap, and 502 when Jev fails;
      - `accepted` is true only for owner answers;
    - §3: uc-engine may call ask, import, confirmed and health, and nginx refuses it everywhere else;
    - §5: the status filter is Pending/Accepted/Changed/All; no thumbnail; the reserved qtypes;
    - §6: plain http is allowed for localhost only; 10 s is a deadline for the whole call; redirects are not followed;
    - §8: Postgres tests run in a throwaway container;
    - §9 step 5: add the web image rebuild.

## Not in this wave (deferred, recorded)

- A cold ask of about 37 batches may exceed the 10 s client deadline. It fails safe as `none`. Revisit when Jev is
  switched on: chunk on the client, or use a longer timeout.

## Verification to paste in the report

- The service suite, plus one Postgres pass on the throwaway `decide-test-pg` (port 55432, `--rm`).
- The decide engine tests (`engine/tests/test_decide_*.py`).
- The web suite (from `D:/PROJECTS/UC MODEL FIXER/web` with `--root <wt>/web`, using the scratchpad config
  `j8-vite.config.mjs`).
- The nginx probe outputs from item 1.
