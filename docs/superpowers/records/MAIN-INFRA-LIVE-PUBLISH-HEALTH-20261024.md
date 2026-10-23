# Publisher health replacement regression

The second local health write failed because PowerShell passed the backup argument of `File.Replace` as an empty path. The runtime now passes `[NullString]::Value`; the first-write `File.Move` path and publication/worker rules are unchanged.

Executed from the owned recovery worktree:

```powershell
pwsh -NoProfile -File tools/tests/live_status_publication_retry.ps1
```

RED: exit1 at the second real health write, `Exception calling "Replace" with "3" argument(s): "The path is empty. (Parameter 'path')"`. Evidence: `data/tmp/health-write-fix/red.txt`, SHA768282b6b38a685fcbe2cfb06333fcc73a8d139efeda553c2a6ad5af51be2f7e.

GREEN: exit0. Actual output:

```text
PASS: upload failure, retry recovery, remote failure, exception, success, bounded networking and retained identity guards
PASS: real first/second atomic health writes and old-handle preservation; fixture=D:\LLM_BACKUP\Codex session\main-infra-live-publish-recovery-20261024\05-Corllenium-UC-Building-Repair-Engine\data\tmp\status-health-620c291fbcdb4db9a1f172848e068b87
```

The new regression extracts the actual runtime health-writing statements and executes them against a newly owned D: fixture. It reads back both JSON versions, holds the old file open with delete sharing through the replacement, verifies that handle still reads the original bytes, and checks the temporary file was consumed. Network commands are existing test doubles; the runtime loop/network publication is not launched by this test.

GREEN evidence SHAe0406d650d6d6769f9ea5d6758ce1926198f747c4c54ab04dd62369e89454ee8. Runtime SHA879a896fec557863f6127d7af1cab55cc2d99773aab2aa3ad8cbfc9c1a7b572a. Test SHA4b77e80d1153b1089ad1dc004e18a544c0d9373d4df0e47bdd7cf4c2d07c0838.

The stopped deployed runtime and logs were preserved. No source exports, geometry, guard, target, live status, server or process was changed. Root controls any new deployment filename and launch.

## Explicit 1F E3 worker registration

The publisher accepts `engine: "E3"` on the existing owned `extra-workers.json` registration. Omitting that field retains E7. Unknown engines are refused. E3 requires exact run ID `MAIN-INFRA-E3-1F-retain-visible-20261024`, floor1F and the owned worker path under the retain-visible worktree's `data/main-infra-e3/run-20261024-1F-retain-visible/execution-1F/worker.json`. Existing PowerShell PID/creation guards remain in force. E3 checking, checked-checkpoint, serialization/finalization and candidate-saved states now carry E3 labels and maintain the correct global running/reviewing state. A saved candidate does not become accepted.

Metadata-only TDD used the actual embedded Python extracted from the runtime, fake progress functions and newly owned D: worker files; no network, model or live progress write occurred. RED:9failed/8passed1.42s, including false E7 labels, absent binding rejection and absent engine rejection. GREEN after the minimal correction:17passed0.49s. Final exact-runtime verification after preserving untouched original line endings:17passed0.29s; PowerShell atomic health/retry regression exit0. Commands:

```powershell
$env:PYTHONPATH=(Get-Location).Path
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -B -m pytest tools/tests/test_live_status_e3_tracking.py -q -p no:cacheprovider --basetemp D:/TEMP/status-e3-freeze
pwsh -NoProfile -File tools/tests/live_status_publication_retry.ps1
```

Final runtime SHA c295f81270c599ef6daa1712b9ffb36419e695501c7ca865f3b849b237f6efea. New test SHA04ec8a050573deabc8cb8a8911b3635b16df78664aa887f9ae368f0f5314776d. RED evidence `data/tmp/health-write-fix/e3-red.txt` SHA cf4b11f8dbc35fee82848b8644d295d769e14e2b385371b6f2861ac0eccb6cb5. Final GREEN `e3-freeze-green.txt` SHA 7e83eda72e1cf39f8e54530aed7f9fddddb67d2dc2a83ae14a4904b62e0d30c3; atomic/retry `e3-freeze-atomic-green.txt` SHA3a9e52b91edb92a4095ddef3dd3ad651ac1711af8339ca8b3ebd2858a00620cc. These evidence files share the same ignored directory. Root must register the actual E3 engine explicitly and deploy a new runtime filename; this change did not alter any running process, worker output or live status.

## Observed 1F E3 history

Only the explicitly registered 1F E3 row gains `worker_events` and `worker_cpu_samples`, each limited to the latest100 entries. Events contain observed_at,engine,run_id,pid,start_utc,phase,message and only available actual kept_edits/rolled_back_edits/output_triangles. They append on a different actual worker phase or bound lifetime, without backfilling earlier phases. observed_at is the observation time, not an invented phase start. Events update last_work_event_at; heartbeat and CPU-only samples do not. CPU samples contain the same lifetime keys plus observed_at and measured cumulative cpu_seconds, while alive and at least30seconds after the previous same-lifetime sample. Missing CPU creates no sample. There is no percentage or ETA.

The PowerShell observation now forwards expected_pid and expected_start from the existing owned registration. The embedded Python rejects an E3 PID mismatch or actual/expected creation-time mismatch using the existing one-second identity floor, preserving the registered start after process exit. Legacy E7 history is unchanged. The remote publication adapter was read: it copies the complete incoming freshMainInfra object, so these row fields survive its existing path without any remote change.

Actual embedded-Python metadata TDD: RED7failed/17passed0.39s, then GREEN24passed0.29s. Final exact-byte GREEN24passed0.30s, plus existing PowerShell publication/atomic-write regression exit0. No network/model/live status operation ran. Exact commands:

```powershell
& 'D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -B -m pytest tools/tests/test_live_status_e3_tracking.py -q -p no:cacheprovider --basetemp D:/TEMP/status-history-freeze
pwsh -NoProfile -File tools/tests/live_status_publication_retry.ps1
```

Final runtime SHA91a2c6f0ee6023ad6c40f3e3c39279d27521e18e5ffc8d6a49bb0b37488c6261; test SHAae0786c2cef14180de4b3e4c7d59b300625f0d1429fdbf157fbc58e7cec2aea8. Evidence under `data/tmp/health-write-fix/`: history-red.txt SHA dbf5c6655681968bb5605de99297134a9abd0ad90616c755be57d6ec0c4822f7; history-freeze-green.txt SHA178f1fa895de679ac029cd5e0295e8695302eac00d0307dd3409ee0bb696d5f5; history-freeze-atomic-green.txt SHAc0d0cc7ecede3589648589d196a392bc296b2accf6252e7a6c8e33a280260400. Root review and a new runtime deployment are still required; current live publisher/output was not changed by these tests.
