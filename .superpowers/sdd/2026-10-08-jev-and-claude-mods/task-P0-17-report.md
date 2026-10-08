# P0-17 report: Jev decision helper (suggest-only, confidence-gated) and `decide-pilot`

Status: DONE_WITH_CONCERNS (concerns below are small; the real-key pilot has not been run, as instructed).
Worktree `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/P0-17`, branch `claude/P0-17`, base `83b89a8`.

## Commits
- `2575300` feat(decide): the wrapper (Decision, JevDecider, group-name and material classifiers), key never printed
- `7e3dc02` feat(decide): the `decide-pilot` command and the pilot measurement, runs without a key

## What I built (files)
- `engine/decide/__init__.py` (docstring only)
- `engine/decide/jev.py`: neutral questions `NoulQ` / `ChoiceQ` / `ScoreQ`; `Decision`; `JevDecider`
  (`ask`, `available`, `calls` log with latency and tokens); key resolution (`read_env_key`, `DEFAULT_ENV_FILE`);
  SDK adapter (`_make_sdk_client`); `classify_group_names`; `classify_materials`.
- `engine/decide/pilot.py`: `load_truth`, `group_rows`, `score`, `run_pilot`, writes `jev_pilot.json` atomically.
- `engine/cli.py`: new subcommand `decide-pilot` (36 inserted lines, nothing else touched).
- `pyproject.toml`: optional group `decide = ["typesafe-sdk"]`.
- `engine/tests/test_decide_jev.py` (22 tests), `engine/tests/test_decide_pilot.py` (7 tests).
- Not touched: `engine/guard/**`, FixProfile, existing tests, `engine/io/skp_writer.py`. `ctypes` is not imported.

## SDK names confirmed against the installed package
Installed with `"$PY" -m pip install typesafe-sdk` into the main venv: `typesafe-sdk 0.7.2`
(+ httpx2, httpcore2, tenacity, truststore). No permission problem. Checked by `inspect` only; no client was created, no network.
- `from typesafe_sdk import TypeSafeClient, Choice, Noul, Score, TypeSafeError, TypeSafeAPIError` all exist.
- `TypeSafeClient.__init__(*, api_key=None, model=None, retry, timeout, ...)`: `api_key` can be passed explicitly (I use that; the key never goes into `os.environ`).
- `system_one(self, state: JSONContent, questions: Mapping[str, Noul|Choice|Score|...], *, model=None, ...)`.
- `Noul(instructions=, criteria=None)`, `Choice(instructions=, criteria: Mapping[str, JSON|None])`, `Score(instructions=, criteria: Sequence)`.
- Response `SystemOneResponse`: `.answers: dict[str, Answer]`, `.model`, `.usage.input_tokens / output_tokens` (may be None), `.nouls/.choices/.scores`.
- `NoulAnswer.noul: float` (no confidence); `ChoiceAnswer.choice: str, confidence, probabilities: dict[str,float]`;
  `ScoreAnswer.score: float, confidence, probabilities: dict[int,float], legend`.
- `TypeSafeAPIError(status, body, headers, message, endpoint)` has `.status`. (The docs' `.request_id` I did not check; I do not use it.)
- Everything matches the controller's docs facts; no difference found.
- The wrapper reads answers by duck typing from `response.answers[id]` (not `.nouls/.choices`), so fakes need no SDK.

## Behaviour decisions (inside the rulings)
- Noul: `answer = p >= 0.5`, `probabilities = {"yes": p, "no": 1-p}`, `confidence = max(p, 1-p)`.
- `state` may be a `str` (sent as `{"text": state}`) or a dict.
- Key: env `TYPESAFE_API_KEY` first, else only that line of the `.env` file (quotes, `export`, whitespace, trailing ` # note` handled), passed to the client explicitly. `.env` path is the constructor parameter `env_file`; the default is `<dir with pyproject.toml>/.env`.
- Failure text: a failed batch records only the exception class name and HTTP status (`Decision.error`), never the message (an SDK message could contain a request line). A failure while creating the client is also an `error` decision.
- Log lines (logger `engine.decide.jev`): question id (cut to 200 chars), source, confidence, accepted, latency, tokens. No state text, no key.
- Instructions are self-contained (ids are not sent to Jev); the state is a short shared task description, the per-group facts are inside each question, so 85 groups x 4 questions = 340 questions = 17 calls at batch 20.
- Building options are the AGENTS.md list plus SITE, labelled `MAIN INFRASTRUCTURE` / `SCIENCE A` and mapped back explicitly to the campus-map keys `MAIN_INFRA` / `SCIENCE_A` (`BUILDING_LABELS`).
- `classify_materials` takes names (str) or dicts `{"name", "texture", "kd"}`; the pilot sends name, texture basename and kd only.

## Failing then passing runs
Red, `test_decide_jev.py` before any implementation (module missing):
```
engine\tests\test_decide_jev.py:13: in <module>
    from engine.decide import jev
E   ModuleNotFoundError: No module named 'engine.decide'
ERROR engine/tests/test_decide_jev.py
1 error in 0.35s
```
Green after implementing:
```
......................                                                   [100%]
22 passed in 1.11s
```
Mutation check that the key-leak test bites (temporarily made `_error_text` return `str(exc)`; restored right after):
```
WARNING  engine.decide.jev:jev.py:221 jev call failed: 1 questions, 401 for key ts-FAKE-KEY-... at https://x/?key=ts-FAKE-KEY-..., 0.00s
FAILED engine/tests/test_decide_jev.py::test_the_key_appears_in_no_repr_log_or_exception_text
1 failed, 21 passed in 2.89s
```
(the key there is the fake test key). Restored: 22 passed.

Red, `test_decide_pilot.py` (see the deviation below: only the CLI test was red):
```
python -m engine.cli: error: argument command: invalid choice: 'decide-pilot' (choose from fix, preview-data, ...)
FAILED engine/tests/test_decide_pilot.py::test_the_cli_runs_without_a_key_and_writes_the_report
1 failed, 6 passed in 5.65s
```
Green after adding the CLI:
```
29 passed in 1.67s      (test_decide_pilot.py + test_decide_jev.py)
```

Tests cover: canned response to Decisions (noul/choice/score); noul derived confidence; `accepted` vs `min_confidence` (edge 0.8 accepted); str/dict state; missing answer = error; 45 questions at batch 20 = calls of 20/20/5 with token/latency log; SDK exception fails only its batch (middle batch); no key = `none`, no client made; no SDK = `none` even with key; injected client available; env beats `.env`; `.env` with other lines gives only the key and `os.environ` stays clean; quoted/bare/empty/missing key file; default env path is the repo-root `.env` (path compared only, never opened); the fake key is in no repr, str, captured log, stdout/stderr, `calls`, `Decision`, including when the client factory itself raises with the key in its message; log line has the question id and no long state; SDK adapter converts to `Noul/Choice/Score` and passes `api_key` and model explicitly (SDK class stubbed, no network); the two classifiers (question shapes, mapping, none path); pilot truth, rows, scoring, end-to-end no-key run, texture file name sent but not the path, CLI.
An autouse fixture points `DEFAULT_ENV_FILE` at a non-existent tmp file, so no test can open the real `.env`.

## Full engine suite (once, at the end)
```
.........................................................x.............. [ 85%]
........................................................................ [ 91%]
........................................................................ [ 97%]
............................                                             [100%]
1179 passed, 1 xfailed in 683.73s (0:11:23)
```
(`engine/tests` only; the controller's 1273 for the base includes `api` tests and the new tests add 29. `git status` is clean after the two commits.)

## No-key CLI run on the real frozen data
Read-only on the main checkout's `data/campus/` files; output went to the scratchpad, not under `data/`. Env var unset, `--env-file` pointing at a non-existent file, so no `.env` was read.
```
$ python -m engine.cli decide-pilot --source <main>/data/campus/source.json --materials <main>/data/campus/materials.json --map <main>/data/campus/campus_map.json --out <scratch>/jev_pilot.json --env-file <scratch>/absent.env
Jev is not available (no TYPESAFE_API_KEY or no typesafe-sdk): every answer is source none, nothing is sent
group names: 85, sources {'none': 340}
  building: accuracy n/a, coverage 0.000 at confidence >= 0.8, accuracy within coverage n/a (85 with truth, 0 unknown)
  type: accuracy n/a, coverage 0.000 at confidence >= 0.8, accuracy within coverage n/a (79 with truth, 6 unknown)
  floor: accuracy n/a, coverage 0.000 at confidence >= 0.8, accuracy within coverage n/a (69 with truth, 16 unknown)
materials: 391, sources {'none': 782}, categories {}
calls: 0 (0 failed), tokens in/out 0/0
wrote <scratch>/jev_pilot.json            (real 2.6 s)
```
The report JSON has `available: false`, 85 groups, 391 materials, a 30-material spot check list, 0 calls.
Truth read from the real map: building counts BRS 16, CHTM 13, EDS 11, ARCHITECTURE 9, MAIN 8, SCIENCE_A 7, SITE 7, PE 7, GYMNASIUM 5, MAIN_INFRA 2 (sums to 85); type known for 79 (floor 69, site 7, element 3); floor known for 69; 2 duplicates (the `excluded` list).

## How the controller runs the real pilot
`PYTHONPATH=<worktree> "$PY" -m engine.cli decide-pilot` from the worktree root (with `--source/--materials/--map` pointing at the main checkout's `data/campus/` since `data/` is git-ignored and absent in the worktree, and `--out data/campus/jev_pilot.json` or a scratch path). The key comes from the process environment, else from the `.env` of the engine's repo root (the worktree root when run from the worktree: no `.env` there, so either export the variable or pass `--env-file <main>/.env`).

## Deviations and concerns
1. Test order: for the pilot I wrote `pilot.py` before the first run of `test_decide_pilot.py`, so only the CLI test was red (6 passed on first run). The wrapper itself was properly red then green. I did add the mutation check on the leak test.
2. Extra files beyond the brief: `engine/decide/pilot.py` and `engine/tests/test_decide_pilot.py`.
3. `Decision` has one extra defaulted field `error: str = ""` (class name and status on a failure); the specified five fields are unchanged.
4. Unit-type truth compares in coarse classes because the map has `floor/element/site` and the brief's Choice has 8 labels: floor->{floor}; element->{stair, roof, shell, other}; site->{road, landscape, bridge, other}. This is my choice and it is stated in the report JSON; the owner may want a different mapping. The 4 multi-unit groups and the 2 groups in no unit have unknown type/floor and are excluded (counts reported: type 6 unknown, floor 16 unknown, which includes element/site groups with no floor).
5. `footprint_building` is computed from vertex bounding boxes (read locally from the frozen OBJs, XY box overlap above 0.5 with the other groups' boxes, other groups assigned by the inventory's name table `building_of`, the group itself left out). So it carries a name-table hint of the neighbours; if the owner wants the pilot to be name-only, drop it. Only the building name and small numbers (tris, z_min, z_max in inches) are sent, never geometry.
6. The pilot's floor accuracy rounds Jev's expected score to the nearest integer before comparing.
7. Not verified: the real network path (`TypeSafeClient` creation and `system_one` with the SDK's objects) has never run; it is covered by an adapter test with the SDK client class stubbed. A Choice with 10 options and a Score with 16 levels are within the documented limits, but real behaviour (e.g. whether `Score.criteria` wants fewer levels) is for the controller's first key run to show.
8. `pip install typesafe-sdk` went into the shared main venv (approved); the wrapper tests do not need it except the adapter test, which skips without it.
9. Line endings: git warns that LF will become CRLF on the new files, same as the repo's existing files; `engine/cli.py` diff is only the 36 added lines.

---

# Fix round (review: APPROVED with Minors)

Commits: `cd9f6d4` (jev.py items 3, 4, 6 with their tests), `bdbfebf` (pilot.py and cli items 1, 2, 5, 7 with their tests). Tests were written first in the two test files and run red together (5 failed, 30 passed; the item-5 CLI test was already green because the code was right, so I proved it bites with a mutation instead). Commits are per source file, not per item, because the test files are shared between items.

Red run (before any implementation):
```
FAILED engine/tests/test_decide_jev.py::test_the_footprint_hint_is_shown_with_the_option_label_not_the_inventory_key
FAILED engine/tests/test_decide_jev.py::test_a_client_that_cannot_be_made_fails_every_batch_at_once_after_one_attempt
FAILED engine/tests/test_decide_jev.py::test_with_several_key_lines_the_last_one_wins
FAILED engine/tests/test_decide_pilot.py::test_a_strict_floor_vs_non_floor_accuracy_sits_next_to_the_lenient_one
FAILED engine/tests/test_decide_pilot.py::test_each_row_carries_its_footprint_hint_and_agreement_is_counted
5 failed, 30 passed in 11.85s
```
1. `groups.type_strict` (floor vs non-floor) next to the lenient `groups.type`, with `groups.type_note` saying "other" counts for both element and site. The CLI prints the strict line too.
2. Every row in `groups.rows` has `footprint_building`; `groups.building_hint` = `{with_hint, jev_agrees, hint_correct, note}` ("Jev plus hint").
3. The hint is shown to Jev through the inverse of `BUILDING_LABELS` (`_LABEL_OF`): `MAIN_INFRA` reads `MAIN INFRASTRUCTURE`, `SCIENCE_A` reads `SCIENCE A`.
4. `_client_or_none` renamed `_get_client`. A failed client creation is remembered (class name and status only); the first batch records one failed call and one warning, later batches (and later `ask` calls) fail at once as `error` with no new attempt and no new warning (test: 45 questions at batch 5, factory called once, one warning).
5. `test_the_cli_never_leaks_a_key_through_a_failing_client`: fake key in a tmp `.env` (with another line), `_make_sdk_client` stubbed to a client whose exception text contains the key; asserts the key is absent from stdout, stderr, captured logs and the output JSON. Mutation check: with `_error_text` returning `str(exc)` this test fails; reverted.
6. `read_env_key` takes the LAST `TYPESAFE_API_KEY=` line (an empty last one means no key); tested.
7. One comment above the `_union_overlap` import in `pilot.py` saying why the private function is reused.

Covering tests:
```
$ ( cd <worktree> && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_decide_jev.py engine/tests/test_decide_pilot.py -q -p no:cacheprovider )
...................................                                      [100%]
35 passed in 3.93s
```
Full engine suite, once at the end:
```
1185 passed, 1 xfailed in 888.50s (0:14:48)
```
`git status` clean after the commits (I did not touch `.superpowers`).
