# MAIN-INFRA-LIVE-OBSERVATIONS-20261024

Fix existing live status publisher's missing common3F checked-replay and independent-validator process observations. Start new owned branch codex/main-infra-live-observations-20261024 from committed publisher1aaaf83c; only publisher source, regression tests and records. Reuse existing canonical writer/publication mechanism; no new service/framework, dashboard/engine/validator/DB changes.

TDD with bounded tinytests: truthful common3F states checking/checked_checkpoint_saved/serializing/finalizing/candidate_saved plus old2F/3F legacy compatibility. Bind registered floor/run/path/PID/exactstart; wrongbinding/stalePID rejects, cannot turn process exit intoPASS. ActualCPU/observation timestamps and bounded event/sample history with no fabricated percentage/ETA. Optional explicit independent-validator registration may refresh realpid/start/alive/cpu without modifying state/verdict/targets/evidence. Canonical ownership remains root;4F-7F read-only reporting unchanged. All existing publisher tests mustpass.

Freeze/review/run tested runtime, then root installs only after matching sourcehash/commit and briefly pauses/resumes only ownedpublisher. Recordactualproductionobservations andpublicreadback; no server/container/API restart or database writes.
