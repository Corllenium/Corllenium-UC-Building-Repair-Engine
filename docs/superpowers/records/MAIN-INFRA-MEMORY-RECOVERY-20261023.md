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

## Live delivery and serial retry start

The filter is LIVE: Siege code58a0f34, durable evidencecd148fd, docs HEADf43f3a5.
Root reopened the actual live1F material/edge screenshot. All95 static files
match both hosting roots and public downloads; API remainsbb71d314. Real login
and logout passed, zero page exceptions,65/65 status polls200,390px no overflow.
2F/3F After stays empty. PR39 remains draft/unmerged; CI account startup limits
are recorded. All43 committed evidence blobs matched saved hashes and sizes.
Durable receipt/screenshots are under the Siege worktree's
docs/handoff/main-infra-live-20261023/inspection/. No heavy browser remains.

Root measured post-browser headroom8.01/8.22/8.16GiB and physical availability
5.71/5.90/5.78GiB at13:00:17/21/24UTC, then authorized exactly one geometry job.
Actual1F E7 attempt2 PID43456, creation13:00:59.5817497Z, exec85048; frozen
planSHA1cd147ad and componentd7e8b14. Tested observerexec51889 retains process
peaks/system commit at a measured approximately2.1s cadence. At13:09:48UTC the
worker was still checking, peak commit2.104GB; system headroom was6.81GiB.

Sole publisher resumedexec1032 after the static hash hold and is atomically
bound to the newPID, creation time and planSHA. Public13:04:03UTC confirms
running1F PID43456, alive, CPU169.16s. The earlier E3candidate10136 remains
explicit inspection only. No new E7 candidate is saved or accepted yet.
2F/3F retries and independent heavy checks remain sequential after1F, each
with a fresh resource gate. Ownership remains Codex1F-3F / Claude Code4F-7F.

## 21:50 +08 — actual retry terminal and source-boundary diagnosis

1F E7 attempt2 PID43456 ended13:36:26.253134UTC, wall2121.56s. Default
kernel final PASS followed three rollback rounds:628planned,273kept,355rolled.
Serializer then failed source-frame `_source_weights` boundary equality; final
1F and staged candidate are both absent. 10,578 is UNSAVED, never a new After.
Independent receipt b0a5f202d6b37628d8e5cc351bf9d221eb005ba3db24ecf833ff3f26fb1389f8
binds failed artifacts and explicitly records independent checks NOT STARTED.
1023 resource samples: observed worker peakcommit2,311,098,368B, minimum global
headroom3,774,504,960B. This attempt passed the previous memory failure point.

Bounded deterministic planner reconstruction matches all628 actual K1 records.
263/273 kept source float proofs pass; ten fail only Shapely barycentric union
by2.7755575615628914e-17 normalized area. Exact Fraction(original binary64)
plane, nonnegative barycentrics, positive winding, exact area and oriented edge
boundary cancellation pass all ten. Literal site2479 fixture SHA
0ffab4d4c34b446a799ea0edc2af25e03dec4d89341161261b6689b0b3dee702;
parent area3/32m². Source positions remain unchanged. A separate TDD serializer
fix is in progress; no epsilon/snap/buffer/guard loosening is authorized.
K1 logs omit exact UV/normal/output bytes: they cannot certify a recovered
original candidate or justify attaching the old PASS to reconstructed geometry.

Status runtime isolated RED reproduced retry reading obsolete worker path;
GREEN1test passed after actual path binding, loading-state support, pending
triangle counts and truthful per-floor failure summary. Owned publisher16316
was creation-time verified then replaced by exec42942. Public13:47:02 readback
reports actual1F source boundary and old2F/3F allocation failures, unchanged
E3candidate URL; both remote roots hash b18c3d8f at13:46:24. Source/model/DB/server
state untouched. Runtime and its bounded fixture are preserved beside this
record under scripts/main-infra/live-worker-status-runtime.ps1 and
scripts/main-infra/test_live_worker_runtime.py.

2F retry wrapper a4898bdd / frozen component531769c / exact floor material maps
remain prepared, not started. Launch gate13:43/13:47 had4.173/4.493GiB commit
headroom; no new heavy job was started into that margin. No foreign app killed.
Codex1F-3F and Claude4F-7F remain separate. UI filter LIVE; no floor accepted.
