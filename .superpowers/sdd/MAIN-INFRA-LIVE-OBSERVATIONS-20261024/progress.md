# Live observations handoff

Code and fixture scope only. The old1aa runtime, canonical/production status and running services have not been changed or deployed. Root installs only the committed exact runtime after independent review, preserving the old runtime/log.

Common3F E3 replay registrations now bind the actual pinned preparation bytes, source revision, floor/run/component, derived worker path and workerP pin, plus observed PID and exact native100ns creation. A worker phase timestamp follows input preflight and is not process creation. The actual60376 creation22:43:56.2456960Z differs from worker.started_utc22:44:08.048445Z; the new path correctly uses the former. checking/checkpoint/serializing/finalizing remain active; candidate_saved remains independent-review pending; dead checking fails, never becomes PASS. Old2F/3F schemas and1F E7/E3 behavior remain supported.

Actual phase events and cumulativeCPU use existing worker_events/worker_cpu_samples fields, latest100, duplicate-phase suppression and30second CPU intervals. Active3F copy keeps the displayed candidate inspection-only. Existing candidate/accepted pointers, prior validation results and evidence stay untouched. Upper4F–7F reporting is unchanged.

Optional extra-validator-workers.json registrations are keyed1F/2F/3F and contain deferred,pid,start,run_id,phase. Exact native PID/creation and nonempty phase/run are required. They always write validator_* audit observations. Existing UI worker_alive/cpu_seconds/observed_at/events/samples update only when the canonical row is already bound to the same PID/exactcreation; root establishes that binding at phaseGO. Other active engine bindings are preserved. A dead prior engine observation cannot erase the canonical validator binding. No validator observation changes floor state, step, blocker, verdict, targets or evidence; a stopped validator stays an observation, not a pass.

Examples are committed beside this record. extra-e3-workers.example.json describes the current common3F worker and deferred2F. extra-validator-workers.example.json is DEFERRED with explicit replacement placeholders; it must be filled from the actual measured process/independent run, and root sets canonical worker_pid/worker_start_utc before enabling. Copying examples to live registry is root's separate installation action, not part of these fixtures.

TDD: common20FAIL/5PASS1.79s; bound-validator handoff1FAIL0.32s; missing/invalid canonical creation2FAIL/1PASS0.42s; displayed-inspection context4FAIL0.80s. Final new29+unchanged24 =53PASS2.86s, observed testtree30,564,352B, no resource abort/all owned exited. All test processes used mainvenv, BLAS1, Dtemp and the existing250MiB bounded observer. No network/model/guard job ran.

Commands from this worktree:
- data/live-observations-tiny-tests/run-bounded.ps1 -Label final-green -TestFiles @('tools/tests/test_live_status_common_observations.py','tools/tests/test_live_status_e3_tracking.py')
- tools/tests/live_status_publication_retry.ps1

The unchanged PowerShell fixture parsed the FINAL runtime, mocked upload/SSH errors and retries, and executed the real D-temp first/second atomic health replacement. BothPASS lines are retained in final-powershell-publication-green.txt, including old-file handle preservation. A preliminary diff check exposed CRLF written by the owned edit script; both owned edited files were normalized toLF and the final53cases/PowerShellfixture/diffcheck rerun succeeded. Exact output/source/test/observer/example hashes are in evidence-inventory.json. Existing tests and transport/atomic health functions have no semantic changes. Root must read actual production/public status after its installation; no live effect is claimed here.
