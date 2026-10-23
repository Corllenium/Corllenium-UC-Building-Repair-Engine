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
