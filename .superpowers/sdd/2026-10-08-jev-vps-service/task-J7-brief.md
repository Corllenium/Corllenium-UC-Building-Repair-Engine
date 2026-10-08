## Global Constraints

- AGENTS.md binds every task: test first; commit after every item; stage files by name; never a bare `cd`; Python is
  `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"`, run from the worktree root in a subshell with
  `PYTHONPATH` set.
- **Branches:** the integration branch `feat/jev-vps` comes from `feat-dashboard` (8b22e75 or later). Each job is
  `claude/<id>` in `.claude/worktrees/<id>` from `feat/jev-vps`. The controller merges with `--no-ff` after a review,
  and asks the repair-engine session before any merge into `feat-dashboard`.
- **Jev is off:** default `DECIDE_JEV_ENABLED=false`. No task makes a real Jev call. Every test uses a fake client.
- **Secrets:** the TypeSafe key is read from the environment only (service). The `uc-engine` password is
  `UC_DECIDE_PASSWORD`, from the environment or else only that one line of the git-ignored repo-root `.env`
  (engine). Neither is ever printed, logged, put in a `repr` or exception text, or committed. Agents never open `.env*`.
- **Never touch:** the live containers `fixer-api`, `fixer-web`, `fixer-db`; the database `fixer`; the VPS. Every test
  database is a throwaway container named `decide-test-pg` on port 55432.
- **The pipeline never waits:** `RemoteDecider` has a 10 s timeout and no retries. Any failure gives `none` / `error`
  decisions, never accepted.
- **Only text leaves the PC:** names, texture file names, categories, small numbers.
- **Limits:** a Score has at most 10 levels and a Choice at most 255 options (`check_question_limits`). The daily cap is
  1,000,000 tokens (`DECIDE_DAILY_TOKEN_CAP`).
- **Logins:** the engine login is `uc-engine`. The owner logins come from `DECIDE_OWNER_USERS` (default `gab`). The
  user name arrives in `X-Remote-User`, set by nginx.
- **Out of scope:** the actual VPS deploy (the controller does it with the owner's OK at that moment), switching Jev
  on, P1-D2, the `repair.next_step` question.


### Task J7: decide-import-pilot (engine)

**Files:**
- Create: `engine/decide/pilot_import.py`
- Modify: `engine/cli.py`, adding the subcommand `decide-import-pilot`
- Test: `engine/tests/test_decide_pilot_import.py`

**Interfaces:**
- Consumes: `pilot.group_rows`, `classify_group_names`, `classify_materials`, `_LABEL_OF` (jev.py); `wire` (J1);
  `RemoteDecider`'s HTTP helper (J6) for `POST /api/decide/import`.
- Produces:
  - `build_import_items(source: dict, materials: dict, pilot: dict) -> list[dict]`, each item
    `{state, question, answer, confidence, model}`;
  - CLI: `decide-import-pilot --url URL --source data/campus/source.json --materials data/campus/materials.json
    --pilot data/campus/jev_pilot.json [--env-file PATH] [--dry-run]`.

- [ ] **Step 1: Write the failing tests** with a small fake `source`, `materials` and `pilot`:
  - **Groups:** the questions are captured by running the real classifiers with a capturing decider. Each group gets
    4 items, matched by the row name in `pilot["groups"]["rows"]`. The building answer goes back to its option label
    through `_LABEL_OF` (`MAIN_INFRA` → `"MAIN INFRASTRUCTURE"`); the floor goes back to its option key (`5` → `"5"`);
    `type` stays as is; `duplicate` stays a bool.
  - **Materials:** only the names in `pilot["materials"]["spot_check"]` produce an item, for `mat.category` only (the
    pilot keeps no confidence for `trim`).
  - **Skipped rows:** a pilot row whose decision has `source != "jev"` or answer `None` is skipped.
  - **Key match:** each item's `wire.question_key(item["state"], question)` equals the key a live call would
    produce for the same row.
  - **Dry run:** `--dry-run` prints the counts and sends nothing.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** Capture the questions with a decider that records `(state, questions)` and returns
  `none`. Pair by the index in the qid (`"<i>:<field>"`) with `rows[i]["name"]` and the pilot's answers. Post in
  chunks of 200 items.
- [ ] **Step 4: Run the tests, then a dry run on the real files:**
  `"$PY" -m engine.cli decide-import-pilot --url http://unused --source <main>/data/campus/source.json --materials <main>/data/campus/materials.json --pilot <main>/data/campus/jev_pilot.json --dry-run`
  Expected: `groups: 340 items (85 x 4), materials: 30 items`, or fewer only where the pilot answer was not
  `source == "jev"`.
- [ ] **Step 5: Commit:** `feat(decide): decide-import-pilot loads the paid pilot answers as pending suggestions`.

---

