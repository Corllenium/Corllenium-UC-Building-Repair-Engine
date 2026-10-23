# Fresh 1F checked E3 pilot qualification

Current measured result, 2026-10-23: E3 completed15856->10136 triangles;280
sites kept/3rolled back. Strict26 guard PASS. Independent signed Validator
textures108392/0 failures and visible coverage5720/0 failures PASS. Overall
FAIL remains on different-look flicker1626,same-look1014,cracks2372. Qualified
walking renders16pairs/0 differences. Generic eye0 was independently found to
be inside a1m cavity, not a valid pedestrian viewpoint. No accepted floor.

Independent2F/3F import qualification is complete. Before-only repair loader
binds actual raw/native/source+engine arrays, frame and MTL/texture assets;
does not require a prior no-op cleanup candidate. RED8, GREEN78passed37.21s.
Actual candidate runs still require strict guard and separate signed validation.
Original source exports, guard/default thresholds and signed targets unchanged.

Saved-pair step: native source indices drive both OBJ exports; no inverse frame
reconstruction. Readback compares full original position/UV/normal tables and
surviving corner indices/winding; material names are compared across OBJ material
renumbering. Input mapping must be integer, sorted, unique and in range before
creating output. Existing output and mismatched source/frame are refused.
Serialization tests observed RED16; unsigned order regression RED1 additionally
proved rejection happened after output creation, corrected by overflow-free order
comparison before writing. Combined GREEN35passed19.69s. Saved mapping still
needs audit/hash integration and independent full-floor validation; no real model
E3 run or candidate acceptance has occurred.

No real E3 repair has run. Base d0d157d retains the signed336 Validator and the
reviewed physical source precision loader. Original fresh exports are untouched.

First step: exact in-memory source-survivor contract and sole checked-E3 wrapper.
Only E3 remove edits can be kept, with a passing non-legacy rollback-enabled site
check. Kept and rejected edits partition the actual plan; a site cannot be partly
kept. Source indices are valid/disjoint. Positions, UVs, normals, winding/material
and precision metadata stay identical; before-input digest rejects mutation.
The wrapper always supplies engines=[E3Hidden(...)], validate_sites=True,
FixProfile() and SiteJudge(looks), with no alternate settings or default engines.

Tests observed RED: initial14 missing-route tests; then4 input-integrity tests
for duplicate face IDs, storage precision changes and in-place source mutation.
Actual GREEN:18 passed in25.11s, including the real default E3 fixture run retaining
all visible facade fixture faces. No source triangles have been removed by a
real-data E3 run. Saved-file binding, independent review and full real pilot
validation remain pending. Old duplicate candidates and their independent FAIL
results remain preserved under the parent run.
