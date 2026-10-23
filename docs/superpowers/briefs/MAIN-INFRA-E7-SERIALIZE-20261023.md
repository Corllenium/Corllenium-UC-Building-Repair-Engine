# MAIN-INFRA-E7-SERIALIZE-20261023

Controller-approved fixture-only serialization job, base b603d39. Separate branch/worktree `codex/main-infra-e7-serialize-20261023`, claimed by Codex-E7-Serialize in the main queue.

Implement the reviewed `docs/superpowers/specs/2026-10-23-main-infra-e7-cut-serialization-proposal.md`. Use original full source position tables, qualified forward-frame engine tables and explicit E3 survivor ancestry. Bind actual checked E7 cuts/outcome and trusted input hashes. Reuse write_floor's precise formatter, existing source digest, kernel apply/log and snapshot hash helpers. No inverse-frame position reconstruction; no new positions. Append only exact checked cut-corner UV/normal rows. Preserve source triangle winding, material names and original polygon/group/object identity. Refuse varying source normals as b603d39 does.

API clarification: prepare_cut_pair accepts the actual `before` MeshData explicitly, because generated input OBJ face lines/material encounter IDs differ from raw source. Original raw polygon identity belongs to the explicit lineage, not read_obj.face_line. The trusted binding names all frozen input files, expected SHA values and actual qualified BEFORE digest; source/engine input meshes are checked against selected original source triangles.

No guard, FixProfile, threshold, Validator, E3 core, source export or existing test changes. No real-floor run, publication or deployment. Deliver pure construction, exact saved source/engine readback, explicit lineage, fail-closed saved binding, and RED/GREEN fixture evidence. Keep the implementation lean. A fresh independent review and native/full signed validation remain later gates.
