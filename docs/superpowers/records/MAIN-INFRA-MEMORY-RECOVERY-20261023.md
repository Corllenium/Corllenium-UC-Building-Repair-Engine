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

## 22:15 +08 — source fix committed and actual 2F retry launched

Source-saving fix94dc8a4b54da572c703f35678bc1165bbbda91a9 is committed in the
separate main-infra-e7-source-proof worktree. Only production file changed is
serializer tools/main_infra_e7_serialization.py, SHA6456ac625441ce9c2649e088247ba73e094995858b074a127d7a54292365a44a.
49focused tests pass locally7.09s and independently5.77s. All273 source cuts
accepted, zero rejected, all628 donor K1 records matched. Actual all273 receipt
5ef4f7d5a395f26ba1284819a35223e0c83a45e2a2dd02f0e88637d4c21f9e3b;
independent linkageb651f602beeee46ed55f4ddeb42804a7a50dc35b7cf954c9f517390ce0b53219.
All11 committed evidence files read/hashchecked. Jobawaitingreview, no core,
weights, guard, signedValidator or threshold change and no saved new1Fmodel.
New attempt3 checked-subset/checkpoint implementation is in a separate claimed
job/worktree; no old PASS may be attached to reconstructed geometry.

Owner replied that they would free memory. Root measured recovery, initially
7.607/7.736GiB; strict8 and7.5GiB trial gates returned NOTSTARTED and wrote no
worker/candidate. After assessment the operational one-worker gate is7GiB,
with three fresh samples; this is not a model guard tolerance. Actual successful
launch samples at14:13:09/10/11 UTC were8.056/7.919/8.187GiB, physical available
4926/4763/5031MiB. Frozen code531769cad83dd6d03214a94cbd21e0209f8f2f33,
runtimea4898bdd79b192b20bb1c40afd31d1623dd3c3d28f06e8fd33c4c7a35ef9190f,
2Fmaterialsf06c1c87d9ceee46e3a5d1c4241059d86dc2bf7e5bf06d09c9f3a95433024df8
were checked before launch. No overwrite or prior failure deletion.

ACTUAL2F E3 attempt2 PID41648, creation14:13:11.8254166Z, exec73109, input56828,
state running_checked_E3. New private run is E3worktree/data/main-infra-e3/
run-20261023-attempt2, console main/data/tmp/main-infra-2F-attempt2-console.txt.
Observerexec37006 records resources-2F.jsonl. At14:15:10 workerprivate596MiB,
peak1341MiB, systemheadroom6.555GiB. Bounded150-250MiB fixture window granted
to attempt3builder; no second heavy geometry/guard/native/Validator/browser.

Rootsolepublisher60916/start13:46:23.0224340Z/exec42942 reads new atomic
extra-e3-workers.json PID/start/path. Actual public14:13:57 reports2Fcleaning,
PID41648/alive/CPU41.75, overallrunning. 1Ffailure remains sourceboundary;
prior preservedE3inspectionasset remains unchanged. 3F remains its old failed
attempt until its actual serial retry. Separate independent2F caller is being
prepared, not run. Codex1F-3F / Claude4F-7F; no accepted floor.

## 23:12 +08 — truthful queued retries, reviewed callers and exporter

Actual 2F E3 attempt2 remains running PID41648/start14:13:11.8254166Z,
component531769c, qualified56828 triangles. At15:06:20 workerprivate1291MiB,
peak1967MiB, systemcommit57,436,819,456/67,303,272,448bytes; no saved candidate
or new failure. A single heavy geometry process remains the operational rule.

The reviewed 1F attempt3 component is18c8ae993cfed71ad7e978d7b253cecb8a1ec5c5:
new checked subset, typed checkpoint captured BEFORE saving, exact source-proof
serializer6456ac62. Independent36fixtures passed15.28s; final reviewf6372781.
Real prepare/run has not started; no old kernel PASS is reusable. 2F independent
caller committed1ac1de3 with53 pinned inputs/0mismatches,30tinytests passed2.53s;
actual guard/native/full Validator waits for saved output and serial memory GO.

The E7 preview exporter now has local52PASS20.14s and independent52PASS23.08s,
reviewb9000bb9; fixtures use real tiny geometry but synthetic external evidence.
Initial independent path-limit-only test failure is retained. No actual E7floor
was packaged or accepted. Root delegated only named reviewed-file commit/records.

Retired failed1Fworker config; all prior attempts/records preserved. New deferred
3F observation regression RED then GREEN1test/0PowerShellparsererrors. Replaced
only owned status publisher60916 while idle; replacement47864 creation
15:08:03.691458Z exec79843. Public HTTP readback15:08:05 reports 1Fqueued,
2Fcleaning/PID41648/alive,3Fqueued. Existing1F E3inspectionpreview10136 remains;
2F/3FAfter stay empty. Full same-turn public artifact is queued-retry-live-
readback-20261023.json beside the tested status runtime. Claude4F-7F unchanged.

### Reviewed exporter committed; checkpoint status regression

E7 preview exporter commit2197243f0bfd4187dba41b3728c1193bb6702168 now contains
exact independently reviewed bytes (reviewb9000bb9) and durable successful52PASS
log plus the prior path-limit-only failed log. No real E7model was packaged.
Sourcefix/attempt3/exporter jobs remain separate, with no engine/guard changes.

A new actual attempt3 state checked_checkpoint_saved exposed another truthful-
status regression: RED reportedfailed, GREEN1test0.135s/0PowerShellparsererrors
now reports cleaning and verified checkpoint saving. Next-action text derives
from observed active floors. Runtime file updated on disk; running publisher
47864 retains its loaded212cd30 version until the next owned restart before1F.
Actual2F remains the only heavy worker; saved independent output still pending.

## 23:38 +08 — actual 1F preparation saved; guarded execution gate

Actual1F prepare-only CLI completed EXIT0/wall36.726s, frozen18c8ae9, planSHA
e5af36dde9a242388985200cd6502b370dba87aba92ef152bec9e91b0f681e2a. All628donor
K1records match;273selected/355excluded;273exact-source+273engine proofsPASS,
rejects0. Original15856/stage10136 remain distinct.14inputs/201components/3donors
rehashed; executiontreeHEADunchanged. Durable readback57b3b69f copied verbatim.
35globalsamples minheadroom7.23GiB. Private/peakINVALID: initial observer tracked
venvlauncher64416, not actual interpreter; never use847872B as worker budget.
No1Fkernel or candidate exists yet. Public15:32:07 shows queued273proofmilestone.

Operational rootreview permits a guarded second1Fworker only after3fresh>=8GiB
headroomsamples, actualchild identity fromlaunch,3GiB private/OSpeakcap and abort
onlynewowned1Ftree ifglobalheadroom<3.5GiB/counteroridentityfailure. Independent
review found reasonable best-effort, not a guarantee. This changes no geometry
threshold or signed guard. Recent600samples min5.880/median8.297/latest8.372GiB;
2Factualpeak1.921GiB, prior1F2.152GiB. Launch still requiresactualgates; at15:37
headroom7.426GiB/no1Fexecuteprocess. No other new heavy process is authorized.

Loaded tested checkpoint-aware3438f3e status runtime by replacing only owned
publisher47864 with4996/start15:35:22.463240Z/exec46920. Newdynamicnextaction uses
observed active floors. Publictwo-rootreadback15:35:24 identical; 2Factual41648
stillrunning,3Fqueued; Claude4F-7F remains separate. Independent1Fattempt3caller
job claimed in separate tree; only bounded TDD permitted. Noacceptedfloor.

## 23:55 +08 — preserve Claude blockers; optional 1F launcher held

Read-only ownership audit: actualClaude5F PID52020/start13:51:56.4222323Z was
alive/private1.20GB;4Fownerstep says checkedE3queued after exactduplicateguard
(noE3workerwitness).6F/7F immutableworkerrecords candidate_saved27108/20625,
ownerreportsblocked due signedremainingtargets. No foreignworker/outputchanged.

Found and corrected a statusmirrorbug: candidate_saved overwrote ownerblocked
withvalidating. GenuinefixtureRED ('validating'!='blocked'), GREEN1test0.200s,
PowerShellparser0errors. Savedcountretained; blocked/failed/cancelled ownerverdict
preserved. Replacedonlyownedpublisher4996 with57300/start15:52:56.585440Z/exec10075.
Public15:53:37 confirms6F/7Fblockedwithactualownerreportedtargetcounts/evidence
summary, 2Fcleaning,1F/3Fqueued. Publicreadbackartifactcommittedbesideruntime.
RootdoesnotclaimindependentgeometryapprovalofClaudeoutputs or adoptassetURLs.

Optional1Fconditionalgate samples15:38were7.8276/7.6605/7.6815GiB (<8), later
7.6..6.8GiB. Noexecuteeverstarted. Independentexternalobserverreviewfoundearly
unboundchildcleanup, unverifiedkill andblockingCIMgaps. RootrevokedGO; agent
stoppedonlyownedobserver63804/start15:45:31.7673815Z andverifiedexit15:49:21.
RootindependentCIM15:49:42foundnoexecute/noobserver. No1Fexecutionnamespaceor
candidateexists; frozen18c8ae9/P e5af unchanged. Observer-only lifecyclecorrection
andnonmodelregressions requireindependentreview+freshrootGO. Actual2F41648
continuescheckedkernel; nooutput/newfailure. Noacceptedfloor.


## 2026-10-24 00:35 +08 - actual 1F saved, independent proof started

ACTUAL1FE7 attempt3 saved10578 source/engine triangles fromstage10136/original15856.
DefaultfreshkernelPASS;273kept/0rollback; verifiedtypedcheckpoint BEFORE saving;
all7newMTL/PNGassets exactqualifiedhashes. ActualPython60308/start16:22:46.8585703Z,
launcher51068/monitor60396/exec21420 exited0 at16:31:19.243954Z. Kernelwall482.12s,
launchwall512.467s; peakcommit1.55GiB/minheadroom5.87GiB; noresourceabort.
Frozen18c8ae9/P e5af unchanged. Newfinalcutb587c3b9/runadb653f7/asset019d965f/
checkpointf6a25830; fullfinalreadbacka73a7462 copied verbatim beside these records.

Earlier v3 startup rejected ownedconhost and stoppedbeforemodelwork;all3owned
handlesexitverified/noWdir. V4narrowclassificationfix9cce3684 independentlyclear;
real_components SAMEHiddenstartupRED->GREEN3.719s/49samples/all10handlesexited.
Actualv4passinggates8.603/8.675/8.712GiB, fullownedtreebudget3GiB/<3.5GiBglobalabort.
ExactreviewedPSbytes preserved withoutGitnewlinefilters. No geometryrulechanged.

Public feed boundactual1F60308+2F41648; now1Fvalidating/pending10578, displayed
E3candidate10136 retained untilnewindependentpreservation/nativeproof. 2Fstill
checkedkernel/nooutput,3Fqueued; Claude4F-7F separate. Publisher57300/exec10075.
Independent1Fcallerdaa5d94/source2ad92656 has36PASS/help0/reviewclear; formaljob
handofftoCodex-Independent-Validator. Its2checkoutCRLFfiles restoredonlyfrom
verifiedcommittedLFblobs; all201components/14inputs/3donors/7assets match, treeclean.
RootGO actual1Fbind/prepare thenfresh>=8GiBgated strict26 -> native33qualified+
13diagnostic -> fullsignedValidator/defaultSettings/targets against ORIGINAL15856.
Singleextraheavybesideexisting2F; owneroperatorindependent. No modelpublication or
acceptedfloor yet. Signedtargets may FAIL; do not weaken or reuse oldPASS.


2026-10-24 00:54 +08: actual independent 1F preparation exited 1 after
75.618 s on caller metadata, before strict guard/native/full signed validation.
The retained original qualified 1F receipt d2ab32f2 has no historical job_id;
its qualified/floor/revision and all four source/engine/reference anchors match.
The failed actual PID15192/result15167ca3/stderrdd981abb remain immutable.
This is not a geometry failure. A narrow caller compatibility fix is committed
3796a0c2: missing historical job_id is allowed, a present wrong/null/blank value
is rejected, and all existing source anchors stay required. The actual retained
schema regression failed before the fix; 44 targeted tests pass afterward.
Independent diff review and a fresh actual preparation retry are pending.
No new 1F E7 model is published or accepted: live shows pending10578 and keeps
the existing independently preserved E3 preview10136 until the new proof exists.
Actual 2F PID41648 remains in the FIRST combined SiteJudge preservation check
(kernel first call, not repeated per-site checks). CPU rose22381.69 to22681.34 s
in118.87 s; one no-locals, nonblocking MainThread dump confirms active ray-lattice
work. No output/ETA/percentage is claimed. 3F readiness55e33ccf and measured glass
factsd78b3dda are copied into this record folder; no 3F engine launch occurred.
The live public status returned200 at16:49:56Z: 1Fvalidating,2Fcleaning,3Fqueued;
all accepted_preview fields remain null. Codex1F-3F/Claude4F-7F split unchanged.
