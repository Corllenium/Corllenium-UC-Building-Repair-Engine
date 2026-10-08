# Jev on the VPS — design (owner-approved section by section, 2026-10-08)

**Status:** design approved in chat on 2026-10-08, sections 1-4. This spec records it. The build is planned in a
separate plan written from this spec.
**Builds on:** spec `2026-10-03-uc-repair-engine-design.md` §9 (Decision hooks and Jev). This document does not
change §9's rules; it decides where Jev runs and how the owner confirms its answers.
**Measured basis:** the Jev pilot of 2026-10-08 (`data/campus/jev_pilot.json`; ledger
`.superpowers/sdd/2026-10-08-jev-and-claude-mods/progress.md`): 57 calls, 0 failed, about 0.3 s per call of 20
questions. At confidence ≥ 0.8: building 97.5 % correct on 95 % of the groups, type 97.2 % on 90 %, floor 95.3 % on 93 %.
Materials: 74 % answered confidently; 23 of 23 correct in a spot check.

## 1. What the owner decided

| Question | Decision |
|---|---|
| Where the owner confirms Jev's suggestions | On the VPS dashboard (PC or phone), behind the existing login |
| Jev's jobs | All four: material categories and campus-map pre-fill **now**; review order (after P4) and fix tie-breaks (after P2) **later**, as new question types of the same service |
| Shape | Approach A: a separate container `uc-fixer-decide` in the existing VPS stack |
| Calls | Live: the engine on the PC calls the service over HTTPS |
| Cost | Each distinct question goes to Jev **once** and is stored for good; it is asked again only when the owner presses "re-ask". Safety cap: **1,000,000 tokens per day** |
| When Jev is used (owner, 2026-10-08, after the design) | **Build now with Jev switched off.** The service, the page and the engine link are built and tested now with zero new Jev calls; the pilot answers already paid for are loaded for review. Jev is switched on **once the repair engine (P2) is ready**, with a new question, **"what is the next repair step for this floor?"**, as a suggestion the owner confirms |

## 2. Rules that do not change (spec §9, AGENTS.md)

- Jev only suggests. It never decides to delete or keep geometry, a guard tolerance or a Validator verdict.
- The engine on the PC uses **only answers the owner has confirmed**. An unconfirmed suggestion is never a fact.
- Only text leaves the PC: names, material names and texture file names, categories, small numbers. Never meshes,
  textures or the model.
- **The PC pipeline never waits on the VPS.** No network, a timeout or an error means rules plus the owner's queue
  only.
- The TypeSafe key is never printed, logged, returned or committed. Agents never open `.env*`.
- Every deploy step on the VPS is an outward action and needs the owner's explicit OK at that moment: the new
  container, the nginx route, the `uc-engine` login and the key file.

## 3. Architecture

```
PC (engine)                                     VPS /docker/uc-fixer (Traefik → HTTPS → nginx login)
RemoteDecider.ask(state, questions) ──HTTPS──▶ POST /api/decide/ask             (login uc-engine only)
  10 s timeout; error/no answer → none          uc-fixer-decide (holds TYPESAFE_API_KEY)
  ◀── answers + suggestion ids ───────────────    owner answer > stored suggestion > Jev (batches of 20)
                                                  stores suggestions in uc-fixer-db, schema `decide`
owner (PC or phone) ──HTTPS──▶ /jev page         POST /api/decide/review/<id>      (owner login only)
engine.cli decide-pull ──HTTPS──▶                GET  /api/decide/confirmed?type=… (both logins)
  → data/decide/confirmed/<type>.json → the only Jev input the engine uses
```

- The existing `uc-fixer-api` stays **read-only** (nginx `limit_except GET`). nginx routes only `/api/decide/` to the
  new container.
- **Two logins in the same `users.htpasswd`:** `uc-engine` may call `ask`, `import`, `confirmed` and `health`, and
  nginx refuses it everywhere else (403 on `/` and on every `/api/` route outside the decide routes; on the owner's
  decide routes the service refuses it). The owner's login may read suggestions, review them, re-ask and fetch
  confirmed answers, and is refused on `ask` by nginx and on `ask` and `import` by the service. nginx enforces this by
  `$remote_user` and passes the user name on as `X-Remote-User`; the service checks it again.
- **Who counts as the owner:** the logins named in `DECIDE_OWNER_USERS` in the service's environment, `gab` by
  default. Any other login, `uc-engine` included, is refused on the owner's endpoints with 403.

## 4. The service `uc-fixer-decide`

**Code:** FastAPI, Python 3.12. It reuses the engine's `engine/decide/jev.py` (JevDecider, the SDK adapter, the
question limits and their key-leak tests), so there is one Jev code path. Image `ucmodelfixer-decide:vps`, built on
the PC and loaded onto the VPS like the other images. Its source lives in `deploy/vps/decide/`, apart from the
dashboard's `api/`.

**Database:** schema `decide` in the existing `uc-fixer-db`. No dashboard table is touched.

| Table | Columns |
|---|---|
| `decide.suggestions` | id; `qtype` (e.g. `mat.category`); `subject` (material or group name); `key` (unique; sha256 of the state + kind + instructions + the ordered criteria, with `qtype` and `subject` not in it, so the same question about the same state is one row); `state` (text, at most 2,000 characters, for display); `state_json` (the full state, jsonb); `question` (json, not jsonb, because jsonb reorders keys and a Choice's option order matters: kind, instructions, criteria, qtype, subject); `answer`; `confidence`; `probabilities`; `model`; `source` (`jev`, `pilot-import`, `owner`); `status` (`pending`, `accepted`, `changed`); `owner_answer`; `reviewed_at`; `reviewed_by`; `created_at` |
| `decide.calls` | id; `at`; `questions`; `latency_ms`; `input_tokens`; `output_tokens`; `model`; `ok`; `error_class`. Never the key, never state text |

**Order of answers, per question:**
1. The owner has confirmed this `qtype` + `subject`: return the owner's answer as source `owner`. No Jev call.
2. A suggestion exists with this `key` (the lookup is by key, see the table): return it. No Jev call.
3. Otherwise ask Jev in batches of 20, and store each answer as a `pending` suggestion.

**Limits, before any call:** Score at most 10 levels and Choice at most 255 options (`check_question_limits`). A
breach answers HTTP 400 naming the limit.

**Jev switch:** `DECIDE_JEV_ENABLED`, which is `false` until the repair engine is ready. While it is off, steps 1 and 2
still answer (owner answers, stored suggestions, pilot imports), and a question that would need step 3 comes back
`none` with the reason `jev off`. No call is made, so no tokens are spent. The owner's "re-ask" button is hidden.
Switching it on is an owner decision, made when P2 is ready; it changes one line in `decide.env`.

**Safety cap:** 1,000,000 tokens per day, summed from `decide.calls`. Over the cap, uncached questions come back as
`none`, with the reason `daily cap`; cached and owner answers still come back.

**Key:** `/docker/uc-fixer/decide.env` with mode 600, holding only `TYPESAFE_API_KEY=`. The owner writes it himself
with one SSH command that prompts for the key, so the key never passes through chat or an agent. The container reads
it from the environment.

**Errors:** a Jev 4xx, 5xx or timeout marks only that batch `error`, with the error class. The call is recorded in
`decide.calls`. The caller gets `source = "error"` for those questions.

**Endpoints:**

| Method and path | Who | What |
|---|---|---|
| `POST /api/decide/ask` | `uc-engine` | `{state, questions}` → `{answers: {qid: Decision + suggestion_id}}`; every answer carries `suggestion_id` (the stored row it came from, or null when none) |
| `GET /api/decide/suggestions?status=&type=&min_conf=&q=&limit=&offset=` | owner | the review list, paged by `limit` and `offset`; returns `{items, counts}` |
| `POST /api/decide/review/<id>` | owner | `{"accept": true}`, or `{"answer": …}`, which must be one of the question's options; a bad answer gets 422 |
| `POST /api/decide/reask/<id>` | owner | ask Jev again for this one suggestion, counted against the cap. It needs a JSON body (`{}` is enough; a form post or an empty body gets 422, which blocks a cross-site trigger). 409 when Jev is off or the daily cap is reached; 502 when the Jev call fails |
| `GET /api/decide/confirmed?type=` | both | the confirmed answers: `subject → answer` |
| `POST /api/decide/import` | `uc-engine` | stores already-answered questions (`pilot-import`) as `pending` suggestions, skipping any already stored; returns `{added, skipped, invalid}` |
| `GET /api/decide/health` | both | ok, the model, today's tokens against the cap, and whether Jev is on |

**`accepted`:** in every answer the service returns, `accepted` is true only when the source is `owner`. Cached,
fresh Jev and pilot-import answers always come back `accepted: false`, with their `confidence` unchanged. The
confidence threshold (`DECIDE_MIN_CONFIDENCE`, 0.8) is a display threshold of the `/jev` page only; nothing is used by
the engine until the owner confirms it. `RemoteDecider` passes the flag through unchanged.

## 5. The page `/jev`

- A new page in the existing dashboard (`web/`), behind the same login, usable on a phone.
- **Tabs:** Materials and Campus map show the pilot answers. Next repair step, Review order and Fix tie-breaks
  show "not available yet" until P2 and P4 add their question types. Their reserved question types are
  `repair.next_step` (Next repair step), `review.priority` (Review order), and `e5.winner`, `e4.same_look` and
  `e8.opening_kind` (Fix tie-breaks). A banner says "Jev is off until the repair
  engine is ready" while the switch is off.
- **Each row shows:**
  - the subject and, for a material, its texture file name as text (no thumbnail: the VPS holds no texture files);
  - Jev's answer and its confidence as a bar;
  - the next 2 options with their probabilities;
  - **Accept**, and **Change**, which offers only the question's allowed options.
- **Filters:** status (Pending, Accepted, Changed, All), minimum confidence, text search. The counts are shown at the top.
- **Accept all shown** asks first ("Accept 143 suggestions?"). Every review records the owner's login and the time.
  A confirmed row can be changed again; the latest answer counts.
- **On the PC's local dashboard** (localhost:5190) the page says "Jev service runs on the VPS" (a 404). On the VPS,
  a 502 (the decide container is down) says "Jev service unreachable".

## 6. The PC side

- **`RemoteDecider`** (`engine/decide/remote.py`) has the same `.ask(state, questions)` as `JevDecider`, so
  `classify_materials` and `classify_group_names` take it unchanged.
  - Timeout 10 s, which is a deadline for the whole call (not per socket operation); no retries inside a pipeline
    run. Unreachable, timeout or HTTP error makes every answer `none` or `error`, never accepted.
  - Plain `http` is allowed for localhost only (any other host needs `https`, because the call carries a password).
    Redirects are not followed.
  - The URL comes from `UC_DECIDE_URL`. The `uc-engine` password comes from the environment variable
    `UC_DECIDE_PASSWORD`, else only that one line of the git-ignored repo-root `.env`. It is never printed or logged.
- **`engine.cli decide-pull --type <qtype>`** writes `data/decide/confirmed/<qtype>.json` (subject → answer) from
  `GET /api/decide/confirmed`. These files are the only Jev input the engine uses.
- **P1-D2** (reserved for this session) registers `RemoteDecider` as the Jev provider behind the rules, once P1-D1's
  Decider protocol is merged. Until then the classifiers use it directly.
- **`engine.cli decide-import-pilot`** stores the 2026-10-08 pilot answers that `data/campus/jev_pilot.json`
  actually holds as `pending` suggestions with source `pilot-import`. That is all 85 groups (4 questions each) and the
  30 spot-checked materials; the file keeps only totals for the other 361 materials. The suggestions are built with the
  same question text and state hash as live calls, so later asks hit the cache and nothing is paid twice. The 361
  materials are asked once when Jev is switched on, for about 100,000 tokens (measured: 40 material calls in the pilot).
  The pilot file has no probabilities, so imported rows show the answer and its confidence only.
  It sends them through `POST /api/decide/import` (`uc-engine` only), which stores a row only if its question is not
  already stored.

## 7. Safety

- Two logins with separate roles. The key exists only on the VPS. The service never returns or logs it.
- Every test database is throwaway, in a throwaway container (`decide-test-pg`, `--rm`). Never the live `fixer`, never `uc-fixer-db`.
- `uc-guard` follow-up, M1c: also deny printing the key from the environment (`printenv`,
  `echo $TYPESAFE_API_KEY`, `Get-ChildItem Env:`). The repair-engine session found this gap.

## 8. Testing

- **Service, unit:** a fake Jev client covers:
  - the order of answers (owner > cache > Jev) and the cache hit;
  - the limits refused before any call, and the daily cap;
  - with `DECIDE_JEV_ENABLED=false`, the fake client is never called and uncached questions come back `none` /
    `jev off`;
  - the roles from `X-Remote-User`;
  - review validation, where the answer must be one of the options;
  - the key never appearing in a response, a log or an exception.
- **Service, API:** the endpoints against a throwaway Postgres 16 container (`decide-test-pg`, port 55432,
  `docker run --rm`; the tests refuse any other port). Never compose, never `uc-fixer-db`.
- **`RemoteDecider`:** a fake HTTP server checks the mapping, that the timeout gives `none`, that a 401 or 500 gives
  `error`, that the password never shows, and `decide-pull`'s file.
- **The page:** the page's logic (the API client, filters, counts and the accept-all selection) lives in plain
  TypeScript modules and is tested with Vitest, as the dashboard's existing tests are. The `.vue` file stays thin.
  No component-test library is added (global rule 6).
- **After deploy, against the real URL:** health, one `ask` as `uc-engine`, one review as the owner, one
  `confirmed` fetch, and one refusal per role (`uc-engine` cannot review; the owner login cannot `ask`).

## 9. Order of work

1. The service and its tests (`deploy/vps/decide/`).
2. `RemoteDecider`, `decide-pull` and `decide-import-pilot` (engine, test first).
3. The `/jev` page (web, test first).
4. Build the images on the PC. The local live containers are rebuilt only with the owner's OK.
5. **Deploy, with the owner's explicit OK at that moment:**
   - load the decide image;
   - rebuild and load the web image `ucmodelfixer-web:vps` (the `/jev` page is part of the bundle), then
     `docker compose up -d --force-recreate web`, which also loads the new `nginx.conf`;
   - add the container to `/docker/uc-fixer/docker-compose.yml`;
   - add the nginx route `/api/decide/`;
   - the owner adds the `uc-engine` login and writes `decide.env` himself, by the prompted SSH commands;
   - run the post-deploy checks.
6. Import the pilot answers, then the owner reviews the first suggestions on `/jev`.
7. Later: P1-D2 (provider behind the Decider).
8. When the repair engine (P2) is ready, with the owner's OK, Jev is switched on with its first live question
   type: `repair.next_step`, "what is the next repair step for this floor?". It is a Choice over the repair steps P2
   defines; its state is the floor's error counts by kind, the steps already run and their Validator results (text
   and small numbers only). Jev suggests and the owner confirms; the engine runs only the confirmed step. Its exact
   options are fixed when P2 names its steps.
9. After that: the P4/P2 question types (`review.priority`, `e5.winner`, `e4.same_look`, `e8.opening_kind`).

## 10. Out of scope

- Running the engine on the VPS (2 vCPU; fixing stays on the PC).
- Supabase. Its schema stays unapplied and is not used here.
- Promotion to AUTO mode (spec §9: at least 95 % agreement over at least 50 decisions). The `suggestions` table keeps
  what that will need, Jev's answer next to the owner's, but no AUTO logic is built now.
