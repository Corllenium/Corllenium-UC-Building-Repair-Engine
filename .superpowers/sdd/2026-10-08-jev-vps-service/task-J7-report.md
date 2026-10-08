# J7 decide-import-pilot - report

Status: DONE. Branch `claude/J7` (worktree `.claude/worktrees/J7`), base e95644f. One commit: `ee193d5`
`feat(decide): decide-import-pilot loads the paid pilot answers as pending suggestions`.

Files: `engine/decide/pilot_import.py` (new), `engine/cli.py` (+39 lines, subcommand `decide-import-pilot`),
`engine/tests/test_decide_pilot_import.py` (new, 20 tests). Nothing else touched: no guard, no `FixProfile`, no
existing test, `remote.py` and `jev.py` unchanged (the helper is reused through `RemoteDecider._call`).

## Red

Tests written first; before the module existed:

```
engine\tests\test_decide_pilot_import.py:9: in <module>
    from engine.decide import jev, pilot, pilot_import, wire
E   ImportError: cannot import name 'pilot_import' from 'engine.decide'
ERROR engine/tests/test_decide_pilot_import.py
1 error in 1.60s
```

## Green

```
engine/tests/test_decide_pilot_import.py  ->  20 passed in 3.16s
the five decide files (pilot_import, remote, wire, jev, pilot)  ->  114 passed in 12.16s
```

The 20 tests: 4 items per group with the building mapped back through `_LABEL_OF` (MAIN_INFRA -> "MAIN INFRASTRUCTURE"),
floor 5 -> "5", type as is, duplicate a bool; every answer is one of its question's options; materials only for the
spot-check names and only `mat.category`; skipped rows (source not jev, answer None, group not in the pilot, answer not an
option); model = the single `calls.models` entry else the pilot's `model`; key match for groups and materials against a
live call through `classify_group_names` / `classify_materials` (`wire.question_key(item["state"], question)`); a material
key matches the ask `run_pilot` makes from `materials.json`; inputs unchanged; CLI: `--dry-run` prints counts and sends
nothing (needs no password and accepts `http://unused`), chunks of 200 (CHUNK patched to 8 for the test: 8 + 8 + 2) POSTed
to `/api/decide/import` with the `uc-engine` Basic auth, counts summed, `UC_DECIDE_URL` fallback, password from the one
env-file line, no password stops before any request, remote http refused, a 422 ends the run with the status only and
no secret, a malformed 2xx reply is an error (BadReply). All against a local fake server on 127.0.0.1.

## Real-file dry run (no network, nothing sent)

```
$ python -m engine.cli decide-import-pilot --url http://unused \
    --source <main>/data/campus/source.json --materials <main>/data/campus/materials.json \
    --pilot <main>/data/campus/jev_pilot.json --dry-run
groups: 340 items (85 x 4), materials: 30 items
dry run: nothing sent
```

No pilot answer was skipped (all 85 x 4 decisions are source jev with an answer; all 30 spot-check categories too).
Consistency checks on the real data (read-only): the rebuilt `group_rows` have the same 85 names as the pilot, and every
`footprint_building` equals the one stored in the pilot rows (0 mismatches); the texture and kd of all 30 spot-check
materials equal what `materials.json` gives (0 mismatches). So the questions rebuilt now are the ones asked then, as far
as these hints show.

## Full engine suite (once)

```
...x.................................................................... [ 90%]
...............................................                          [100%]
1270 passed, 1 xfailed in 775.09s (0:12:55)
```

## Notes and concerns

- Rules touched (AGENTS.md 3-6): none of the geometry rules apply; no guard, vertex or visible-surface change. Only text
  leaves the PC when a real run is made; this job made no real run.
- `probabilities` is sent as `{}` (per the ruling). `confidence` is the pilot's float. `model` is the pilot's real model
  (`jev-1.13.0`, from `calls.models`).
- `import_items` uses a 60 s timeout per chunk (not RemoteDecider's 10 s ask timeout), since a chunk of 200 rows is a
  database write. A failed chunk ends the run; chunks already sent stay (the service reports `skipped` for rows it has).
- A live-send was never done: the real POST path is tested only against the local fake server. The reply shape
  (`added`/`skipped`/`invalid` as ints) is as the dispatch gave it, not checked against the merged J-service code here.
- The key check proves the stored question equals the classifier's question for the same row. It cannot prove the
  campus data is unchanged since the pilot ran beyond the footprint/texture/kd comparisons above (tris and z are not
  stored in the pilot file).
- Git warned that LF will become CRLF in the two new files (autocrlf); harmless.

## Review fix round (3 Minors)

One more commit on `claude/J7`: see `git log` (message `fix(decide): decide-import-pilot skips and counts unreproducible groups, ...`).

1. `build_import_report(source, materials, pilot) -> (items, unreproducible)` (`build_import_items` is a wrapper). A group
   is skipped and listed when its rebuilt `footprint_building` differs from the pilot row's, or when `z_min`/`z_max` is
   None (snapshot OBJ missing). The count is printed in the dry run (`unreproducible: N`, plus the names) and in the real
   output (`imported: added A, skipped S, invalid I, unreproducible N`). Tests: footprint differs, missing snapshot, clean
   run gives none, CLI dry run and real output both report it.
2. Labels: `groups: X items from Y groups, materials: Z items from W spot-check materials, unreproducible: N`. Tested.
3. Test added for a spot-check name missing from materials.json: texture and kd come from the pilot, and the key equals a
   live classifier ask with those values. (It passed on first run: the fallback already existed, it was untested.)

Red before the fix: 5 of the new/changed tests failed (missing `build_import_report`, old "(4 x 4)" label); the
fallback test was green at once, as noted. Green after: `test_decide_pilot_import.py` 25 passed; the five decide files
119 passed in 11.23s.

Real dry run again (no network):
```
groups: 340 items from 85 groups, materials: 30 items from 30 spot-check materials, unreproducible: 0
dry run: nothing sent
```
