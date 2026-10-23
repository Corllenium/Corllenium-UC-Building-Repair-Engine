# Main Infrastructure: shared memory exhaustion and recovery

All three actual lower-floor workers failed at 12:20:17 UTC on 2026-10-23:

| Floor | PID | Failed allocation | Wall seconds |
|---|---:|---|---:|
| 1F E7 | 56540 | 1.97 MiB, float64 (258102,) | 1637.08 |
| 2F E3 | 53936 | 11.4 MiB, bool (70,56828,3) | 5004.47 |
| 3F E3 | 56832 | 1.46 MiB, float64 (63691,3) | 4959.26 |

Windows Resource-Exhaustion-Detector/Operational Event 1003, record 823,
12:20:17.9077837 UTC, directly measured system commit
67,057,364,992 / 67,303,272,448 bytes (99.63%). An independent agent queried
the original event XML and corroborated these counters. There is no evidence
that lowering guards, changing targets or reducing visibility measurements is
needed. No new candidate/audit was saved by any of the three failed workers.
Their receipts, traceback logs, preparation and frozen inputs are preserved.

Failure evidence lives under the E7 execution tree:
`data/main-infra-e7/run-20261023/execution-1F/windows-exhaustion-counters.json`.
Independent readback is under the E3 run:
`independent-validator/1F-e7/initial-attempt-failure-readback.json`, SHA256
158040a798c2c061d2a4060b187ebbbff3f3d9e2630a4c7227f7208e968a0d92.

Stopped only the owned broad test tree (pytest 54096 and launcher 56660),
which used about 885.6 MiB private commit. The incomplete suite had recorded
542 passes and zero failures; it is not a full-suite pass. No foreign app,
Claude worker, server, Docker container, database or Windows pagefile was changed.

Prepared sequential retries, not yet started in this record:

- 1F E7: committed tree d7e8b14e60e24fa08c569dda5ca937d9c42a7628,
  same engine component and input hashes, fresh run-20261023-attempt2;
  preparation SHA256 1cd147ad337153811478b6f7a02e904f8fd935227aefa89ef794b5b8abc4896f.
  A tested external observer records process peaks and system commit.
- 2F/3F E3: owned component 531769cad83dd6d03214a94cbd21e0209f8f2f33
  retains the fec7b3e qualified loader and ports only the independently reviewed
  finite ray index. RED 7 failed/1 passed; GREEN 31 passed in 1.95s. Signed
  checks, guard, kernel, SiteJudge, Profile and loader are unchanged.
  Prepared runtime SHA256 a4898bdd79b192b20bb1c40afd31d1623dd3c3d28f06e8fd33c4c7a35ef9190f
  changes only output namespace, preserves original qualifier paths and asserts
  the exact component commit. Independent compile/diff review passed.

Wait for the dashboard build/browser release, measure system headroom and run
one geometry worker at a time. Resource headroom is an orchestration choice,
not an owner validation tolerance. Every new saved receipt gets a separately
pinned independent caller against the original fresh export; failed attempts
and prior first-check verdicts are never reused as passes.

Live status now truthfully reports the allocation failures and recovery step.
The lightweight publisher continues in session 88873; both output roots retain
atomic write/readback and 0644 permissions. Its isolated failure fixture passed
for truthful stage, string logs, exact fresh payload and unrelated-data retention.
No static model or server state was changed by this status correction.

The owner's new colour-inspection filter is committed in Siege 58a0f34.
35 focused tests, typecheck, changed-module lint and the 33-route production
export passed. Actual compiled/live visual verification and publication are
still pending in this record. Colours identify exact materials; they are not
legacy error masks or a visibility pass.

Ownership remains Codex 1F-3F / Claude Code 4F-7F. The prior 1F E3 candidate
still passes preservation but fails remaining targets; no floor is accepted.
