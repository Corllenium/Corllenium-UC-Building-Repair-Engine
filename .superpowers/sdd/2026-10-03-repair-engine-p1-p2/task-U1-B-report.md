# Task U1-B report (plan Task 6: mirror project and importer sync)

Worktree `.claude/worktrees/U1-B`, branch `claude/U1-B`, base 7258652.

## Commits
- 63b3298 feat(unity): sha256-checked sync of the owner's importer into the mirror project (tools/unity_mirror.py, tools/tests/test_unity_mirror_sync.py)
- a345018 feat(unity): the mirror Unity project (6000.4.7f1), created with -createProject (unity/ImportMirror/.gitignore, Packages/manifest.json, Packages/packages-lock.json, ProjectSettings/*)

## Tests
- Red: `tools/tests/test_unity_mirror_sync.py` failed with `ModuleNotFoundError: No module named 'tools.unity_mirror'`.
- Then with the plan's byte-hash `_sha`: 3 passed, `test_a_utf8_bom_does_not_change_the_hash` FAILED (`assert (False)`), the right reason.
- Green after `_sha` = `hashlib.sha256(p.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()`: 4 passed.
- Full tools suite: 184 passed (180 before + 4 new).

## Unity createProject
- Command: `Unity.exe -batchmode -nographics -quit -createProject <worktree>/unity/ImportMirror -logFile C:/Temp/u1/create.log`, run in the background.
- Exit code 0 (log ends "Exiting batchmode successfully now!"). Created ProjectSettings (ProjectVersion.txt: 6000.4.7f1, f3c3c4248748), Packages/manifest.json, Packages/packages-lock.json. No licence problem.
- Library, Logs, Temp, UserSettings are on disk and ignored by the .gitignore; `git status` is clean after the commit.

## Sync and check (real run)
```
b6b88ebd419d62386a95dfad17f69baef0a735db5d9e61c6febdae786893c19e
OK mirror=b6b88ebd419d62386a95dfad17f69baef0a735db5d9e61c6febdae786893c19e owner=b6b88ebd419d62386a95dfad17f69baef0a735db5d9e61c6febdae786893c19e
check exit=0
```

## Notes and concerns
- The hash is of the decoded text, as the brief asked. `read_text` also folds CRLF to LF, so the value (b6b88e...) differs from the raw-byte `sha256sum` of the owner's file (ea37ed...). Both sides use the same function, so check is consistent. Anyone comparing with `sha256sum` by hand will see a different value. This also means a line-ending-only change by the owner does not count as stale.
- Nothing was written to the owner's Unity project (the importer was read only; its mtime test is covered). `unityvcstray.exe` was already running (not mine, left alone). No guard, FixProfile, engine or existing test file touched.
- No geometry is affected, so the golden-unit Validator run does not apply to this task.

## Follow-up fix (coordinator request): commit 0814609
- `_sha` is now `sha256(p.read_bytes().decode("utf-8-sig").encode("utf-8"))`: BOM stripped, CRLF kept byte-exact (matches the C# exporter's File.ReadAllText).
- New test `test_a_line_ending_change_makes_the_copy_stale`: red first (`assert (not True)`), green after the fix. BOM test kept. 5 passed in the file; tools suite 185 passed.
- sync/check: `OK mirror=ea37ed71d057537c260a0048217b607859972e16ac82a8d667de1927b7e49732 owner=` the same value. This now equals the raw `sha256sum` of the owner's file (it has no BOM), so the earlier note about differing hashes no longer applies.
