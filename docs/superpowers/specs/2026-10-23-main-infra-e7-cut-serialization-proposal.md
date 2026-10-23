# Exact E7 source/engine cut pair: proposal for controller review

Status: the controller reviewed this proposal and approved fixture-only TDD implementation as separate job MAIN-INFRA-E7-SERIALIZE-20261023. The corrected E7 planner base is b603d39. The job brief clarifies the actual BEFORE argument and existing qualification/provenance schema. Real-floor execution and publication remain unauthorized in this job.

## Reuse and interface

Reuse `engine.io.minecraft_floor.write_floor` and its existing `_number` formatter (`Decimal(repr(float(value)))`): this formatter already roundtrips float64 values. Do not use generic `write_obj`, which rounds UV/normals to six decimal places. Do not modify E3's survivor-only writer or bypass it with a new mode.

Proposed new module `tools/main_infra_e7_serialization.py`:

- `prepare_cut_pair(source_floor, engine_floor, before, input_lineage, outcome, looks, *, binding) -> CutPair`: pure validation and construction, no output paths touched.
- `save_cut_pair(pair, out) -> receipt`: write a new owned package, reread both OBJs and all manifests, then finalize only if every proof matches. Refuse an existing output directory.
- `bind_saved_cut_pair(source_floor, engine_floor, before, input_lineage, looks, candidate, *, binding, expected_receipt_sha256) -> (source_after, engine_after, receipt)`: independent saved-artifact binding for the subsequent guard/Validator loader. No new Validator setting or threshold.

The caller supplies independently qualified inputs; this module does not infer units, triangulate original n-gons, construct inverse-frame positions or qualify its own source.

## Inputs and trusted binding

`binding` contains expected SHA256 values for the original frozen raw source, native triangulation reference, qualification receipt, stage-input source OBJ, stage-input engine OBJ, existing source-face lineage, original assets and recorded E7 edit log. It names the single qualified source-to-engine frame and both meshes' precision metadata. Hash the actual files before reading, then verify the loaded table digests against the objects handed to the serializer. The serializer must reject a changed file or a different in-memory mesh even if a caller supplies a newly computed self-consistent hash elsewhere.

`source_floor` is the qualified original source-domain FloorInput, with original full position/UV/normal tables and original SourcePolygon metadata. `engine_floor` is its qualified forward-frame counterpart, retaining the original vertex-table indexing. For an E3-following E7 stage, `input_lineage` is the already hash-bound E3 survivor map: each stage-input face indexes its original fresh source triangle. Reconstruct both stage-input face sets by selecting those original triangles; do not assume an intermediate read_obj.face_line names a raw Minecraft polygon.

Prove that original source positions remain bit-identical and that the engine input table equals the qualified forward transform. Normal tables are bound to the recorded proper rotation. UV tables and corner indexing are shared. Asset bytes and material names are unchanged. No position row is added, dropped, reindexed or reconstructed from the engine frame.

## Bind the actual checked outcome

Require exactly one nonlegacy E7 stage and no legacy result/stages. Every planned edit must be a one-original-face `cut`, with no new_points, no add/remove/flip, valid existing indices and disjoint source faces. Kept and rolled-back edits must partition the actual plan by identity; a site cannot be partly kept. Any kept edit requires that stage's last fresh rollback-enabled check to be PASS. A stage keeping nothing serializes its input only, with explicit NOTHING KEPT/PASS evidence as applicable.

Recompute original K1 keys using the qualified Looks, but do not treat K1 as an attribute proof: K1 ignores UV/normals. Reapply only the actual kept edits through existing apply_edits and require the result's positions, UV/normal tables, corner indices, material names and metadata to match outcome.mesh exactly. Compare the actual kernel records to the recorded edit log. Persist a canonical `checked-edits.json` payload containing every original planned cut (source face/site/reason/vertex rows/per-corner values), kept and rolled-back sets, the actual check object, input digests, edit-log hash and checked outcome array digests. JSON must reject nonfinite values; no guessed or reused PASS.

For each kept edit, rerun the same source-triangle shape and attribute proof. Validate that the cut changes only its original triangle and creates no position. New UV values must equal that original triangle's interpolation using the same engine-domain barycentric weights that produced the checked cut. Build new source normals from those same weights applied to the original source normal corners, then prove the recorded forward rotation gives the checked engine values. Never inverse-transform positions. If a bit-exact normal-frame proof fails, refuse it rather than rounding.

Review issue: affine normal interpolation preserves the mathematical source vector field, but a shader that normalizes at vertices may shade varying normal corners differently after a split. The approved delivery rule refuses nonconstant per-face normals unless the actual renderer is separately proven equivalent. This is an admission restriction to review before any real run, not a proposed guard relaxation.

## Deterministic tables and face order

Keep the original full positions table byte-for-byte in each frame. Keep each frame's original UV and normal tables as an exact prefix. Append exactly the rows that existing apply_edits creates for kept cut corners, in its deterministic first-occurrence order; every appended row must be referenced by a kept child. No fitting, normalization, material substitution or extra table rows. Current apply_edits deduplicates appended values among themselves, but may repeat a value already in the original prefix; retaining that checked layout is preferable to silently reindexing the actual outcome.

Use kernel face order: unchanged stage-input faces in their original order, followed by children in kept-edit order and each edit's original child-row order. Do not sort child geometry after checking it. E7's planner already orders source faces. Reapplying the same checked outcome must produce identical OBJ, lineage and checked-edits bytes.

For the source-domain mesh, use the original source positions and source original corner attributes as the prefix; append only the derived source cut-corner attributes. Faces use the exact same existing vertex IDs as the checked engine mesh. Preserve each original triangle's winding and material name. For write_floor, synthesize one output SourcePolygon per output triangle using that triangle's corner indices and its original ancestor's group/object/material metadata; triangle_polygon is an identity map and triangle_corners is [0,1,2] for those output records. The separate lineage retains the original polygon relation, so this does not pretend a threaded point was an original n-gon corner. Do not export rebuilt n-gons.

## Explicit output lineage

`cut-lineage.json` version 1, mode `original_source_existing_vertex_cuts`, binds both input OBJ hashes, input lineage hash, checked-edits hash and both output OBJ hashes. Each output face row records:

- output face index and corresponding stage-input face index;
- original fresh source triangle ID and original raw polygon line;
- original object/group/material name;
- unchanged or cut_child; actual plan edit index/site and child index when cut;
- existing vertex IDs and source/engine UV/normal corner indices.

An unchanged row has no cut edit/site and retains its original corner indices. A cut row names exactly one source triangle and appears exactly once in its actual edit's children. Every output face has one row; every kept cut child has one row; rolled-back edits contribute no children. Persist original polygon lineage separately from new OBJ physical line numbers to avoid the earlier eye0 scratch label mistake.

## Saved readback and receipt

Read both actual saved OBJs with the existing reader. Require bit-identical float64 position, UV and normal tables (dtype/shape/bytes, including signed zero), exact vertex/UV/normal index rows, expected winding and material name per face. Readers may number material names by encounter; compare face material names and record the explicit table-name mapping rather than claiming numeric IDs are the material identity. Verify object/group state against emitted records and lineage. New physical OBJ face line numbers are derived from the saved file and are not compared to original raw polygon lines.

A versioned receipt binds all trusted input hashes and metadata, actual checked-edits/edit-log hashes, output and lineage hashes, table digests, counts of unchanged faces/cut originals/children, explicit no-position-change results, exact readback results and unchanged asset inventory. It states candidate-only, not accepted/validated floor. The caller provides the trusted expected receipt hash to later binding; a modified receipt does not validate itself.

Write to a fresh owned staging directory under the output parent. Finalize the requested new directory only after all readbacks pass. Any failure leaves only clearly labelled owned diagnostics; it cannot replace a previous accepted/candidate package. Do not rotate the global preview run or publish dashboard assets here.

## Proposed TDD scope after approval

1. Literal seam pair with nonbinary UV values: exact float64 roundtrip of both frames, original position-table identity, deterministic children and lineage; avoid a fixture whose values all fit six decimal places.
2. E3 survivor ancestry plus kept and rolled-back E7 cuts: unchanged faces/corners survive, only kept children appear, original polygon/group/object/material identities remain.
3. Reject tampered input/hash/frame/precision/log/map/check/receipt; reject added/reindexed/moved positions, wrong source triangle/child ordering, attribute swaps, missing/extra children, changed material, unconfirmed cuts and fake PASS partitions.
4. Source/engine normal rotation proof and absent corner attributes; conservative varying-normal refusal if approved.
5. Readback failure is fail-closed and output directories are never overwritten. Real qualified native and independent full-floor checks remain later gates; no real-floor run occurs in serializer implementation tests.
