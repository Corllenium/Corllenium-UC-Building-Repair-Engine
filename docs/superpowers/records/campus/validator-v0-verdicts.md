# Validator v0 verdicts on today's engine outputs (job P0-16, 2026-10-08)

The Validator (`engine/validate/`, P0-14 and P0-15) was run on three real units, with the BEFORE the output was
made from and the AFTER the old engine wrote. All three FAIL, as expected: today's engine predates the owner's
strict rule (AGENTS.md section 5 and 6), and v0 has no allowed change classes, so every change counts. This is
the list of what P2's engines must stop doing, or must show with a picture.

- Commands: `python -m engine.cli validate --before <snapshot> --after <fixed.obj> --materials data/campus/materials.json --out <dir>`,
  default density (area per sample 36, at least 4 per face; no development-run note), targets unsigned.
- Outputs (not committed, in the temp folder): `C:\Users\Future26\AppData\Local\Temp\claude\p016\{chtm5,sideA,sideB}\validation.json`
  and `evidence\site-NN-{before,after}.png`.
- The CHTM 5th floor BEFORE is the very file the AFTER was made from: `report.json` `input_sha256` equals the
  sha256 of `data/snapshots/c0c877002500-b7c2dc01/chtm_5ft_floor.obj` (c0c877002500...).
- Check 2 (problems) is REPORT_ONLY until the owner signs targets, so every verdict comes from checks 1 and 3.
- Reading the crops: they are coloured by LOOK (grey, brown, dark teal ...), a face seen from behind is PURPLE.
  A UV failure changes no colour, so no crop can show it; the counts carry it.

## Summary

| Unit | Verdict | Samples seen in BEFORE | Failing (check 1) | By reason: covered / overlaid / deleted / look / uv / side | Check 3: deleted / replaced / covered / overlaid | Sites (with crops) | Time |
|---|---|---|---|---|---|---|---|
| CHTM 5th floor (`chtm_5ft_floor`) | FAIL | 275,918 | 39,985 | 4,796 / 3 / 21,242 / 799 / 13,118 / 27 | 21,312 / 808 / 4,806 / 3 | 75 (20) | 579.6 s |
| Sidewalk A (`CHTM_SIDE_WALK_2nd_floor`, snapshot ce26e0392ab0) | FAIL | 41,636 | 9,554 | 2,943 / 26 / 54 / 0 / 6,067 / 464 | 173 / 0 / 3,199 / 29 | 10 (10) | 31.0 s |
| Sidewalk B (`CHTM_2nd_to_3rd_building_sidewalk_outside`, snapshot 0b290ec0bcb4) | FAIL | 91,154 | 25,413 | 8,118 / 5 / 59 / 0 / 16,833 / 398 | 107 / 0 / 9,183 / 5 | 25 (20) | 92.4 s |

Check 2, before to after (reported, not judged):

| Unit | flicker_diff | flicker_same | reversed | hidden | loose | open_edges | cracks |
|---|---|---|---|---|---|---|---|
| CHTM 5th | 5668 to 116 | 4793 to 53 | 29 to 21 | 12870 to 1232 | 1055 to 1 | 346 to **1921** | 3884 to 9 |
| Sidewalk A | 0 to 0 | 530 to 40 | 809 to 24 | 1853 to 66 | 221 to 13 | 250 to **378** | 550 to 32 |
| Sidewalk B | 321 to 0 | 1026 to 4 | 838 to 0 | 2411 to 27 | 79 to 4 | 326 to 134 | 559 to 25 |

Open edges rise on CHTM 5th and Sidewalk A: the fix opened borders where it removed faces.

Notes the Validator wrote: Sidewalk A has one material not in `materials.json`
(`mumi_littletiles_ltstone_-7`), compared by name with its texture size and colour from the snapshot's own MTL
(its UV was compared). The other two have none.

Samples (`validation.json` viewpoints): CHTM 5th had 1,403 eye-height probes, A 465, B 838; 128 outside
directions, 24 cameras, 1,024 extra directions each.

## What the evidence says, per unit

### CHTM 5th floor: deleted visible faces, flicker losers, UV, covers

Counts: **21,242 samples deleted** (area about 697,000 sq in), 799 in another look (808 in check 3), 13,118 UV
changed, 4,796 covered, 27 seen from behind. 8,052 faces were seen, 2,103 failed, 1,274 of them have no sample
met at all.

Crops opened (the 8 worst sites of 20, seen as BEFORE | AFTER):

1. **Site 1** (1,396 in wide, 21,859 samples: 13,287 deleted, 5,803 uv, 2,329 covered). BEFORE: one brown surface
   broken by many dark teal and black rectangles and strips, purple strips along its edges. AFTER: nearly flat
   brown, one black slit, a wide purple band along the bottom. A whole second look that BEFORE showed is gone,
   which matches `flicker_diff` 5668 to 116: the engine kept one side of each different-look overlap and the Validator
   counts the other as deleted.
2. **Site 2** (441 in, 5,522 samples: 2,226 deleted, 354 look, 1,019 uv, 1,919 covered). BEFORE: black triangle and
   strips beside a narrow white slot. AFTER: those black parts are violet blocks and a violet triangle, so
   what was dark is now another look, seen from behind in places.
3. **Site 3** (553 in, 5,365 samples: 3,979 deleted, 1,322 uv). BEFORE: speckled purple and grey at the upper
   corners (z-fight noise from stacked faces). AFTER: solid purple blocks, the noise gone, the white window opening
   unchanged. The deletion is the noise layers.
4. **Site 9** (261 samples, all deleted): a brown wall with a square opening. BEFORE: the opening's reveal shows
   black and teal below a purple strip. AFTER: the reveal is violet with a diagonal split. The reveal faces are
   gone or replaced.
5. **Site 15** (109 deleted): a brown surface with a square frame. At crop size the two crops are almost the same;
   only the violet strip at the lower left of the frame differs. A real but small loss.
6. **Site 11** (144 covered, 3 faces): a grey wall with a dark doorway. BEFORE: the doorway is black to its full
   height. AFTER: the top part of the black is grey. Something now stands in front of the upper doorway: that is a
   cover of a visible surface.
7. **Site 20** (66 covered, 1 face): a dark olive and purple interior with a pale column. AFTER has a large new
   violet triangle in the upper right and a changed column base: faces now cover what BEFORE showed.
8. **Site 5** (1,027 uv, 46 covered): a grey wall with two window frames. The crops are identical by look, because a UV
   failure changes no colour. The counts are the only evidence.

Independent check of the samples (my own brute-force script, not the Validator, 250 random failing samples per
reason, parallel faces within 0.25 in of the point):

| Reason | What the sample points show |
|---|---|
| deleted | in **250 of 250** there is no AFTER face within 0.25 in; in 147 of them BEFORE had two or more coplanar layers there. The Validator's finding is confirmed by a second method, not a false alarm. |
| look | in 250 of 250 BEFORE had stacked layers there and in 249 AFTER has a coplanar face of OPPOSITE winding: the back-to-back or different-look flicker pairs, the engine kept one side. P2's E5 cut or the owner decides these (AGENTS.md section 5). |
| uv | in 235 of 250 AFTER has a same-winding coplanar face (the geometry stayed, its UV changed); in only 16 BEFORE had stacked layers. Of the UV errors, 79 % are small (median 0.0054 tile, 1.4 texels on a 256 px texture, just past the 1-texel tolerance) and 18 % large (up to 0.35 tile). The small ones are on UV values near 3, so the OBJ's 6-digit print precision is NOT the cause (I checked). Cause not identified. |
| covered | in 150 of 250 AFTER has a same-winding layer at the point (something else is in front); in 78 nothing coplanar is left |

So: the deleted and look failures are real and expected (v0 has no allowed classes). The UV failures are real
changes, but 79 % of them are about one texel: whether the 1-texel tolerance is meant to be that strict is
for the owner (I did not touch it).

### Sidewalk A (`CHTM_SIDE_WALK_2nd_floor`)

Counts: 9,554 of 41,636 samples fail: covered 2,943, **uv 6,067**, side 464, deleted 54, overlaid 26. 10 sites, all with crops.

Crops opened (BEFORE | AFTER; sites 1 to 5, 7 and 8):

1. **Site 1** (5,972 samples; 1,006 in wide). BEFORE: stepped blocks of purple (faces seen from behind) along the left
   edge of a grey surface. AFTER: all grey, no purple. The picture got cleaner while the Validator still counts 4,091 uv
   and 1,499 covered here.
2. **Site 2** (3,070 samples). BEFORE: purple triangles at the lower left diagonal and the upper right. AFTER: the lower
   ones are gone, the upper right ones remain (the 120 `side` samples).
3. **Site 3** (715 samples; 314 uv, 401 covered). A sloped band: BEFORE a patchwork of grey and purple (front and
   back faces flickering); AFTER one solid grey band.
4. **Site 5** (36 samples). A large side face: BEFORE broad purple regions with grey blocks inside; AFTER one even grey
   face above a darker one, no purple.
5. **Sites 4, 7, 8** (edge-on slab, thin ribbons): BEFORE has several purple ribbons and light patches along the slab;
   AFTER has fewer, with some purple left. Too thin to read more.

Independent check: 300 sampled UV failures: in 286 BEFORE had a single layer there and **276 of those do not match any
AFTER layer in UV**, so the UV change is real (in the examples I read, the offset differs by 0.26 to 0.47 tile between two BEFORE faces that
the merge put under one UV frame; the UV density is the same for 4 of the 6 faces I measured, ratio 0.998 to 1.002, and 0.68 and 0.11 for the other two). But the one material is
`ltstone_-7`, a 16 x 16 texture with a standard deviation of 3 of 255 grey levels (the image is almost flat grey):
a UV shift there is, I expect, close to invisible. The Validator does not know a texture's contrast; the rule as
written counts it.

The 3,199 covered: of 400 sampled covered points, 338 (along the normal) and 336 (against it) meet an AFTER face 4 to 330 in away
(median 22 and 30 in), facing the viewer in 90 %. That is what a closed rebuilt slab does to inner faces that BEFORE showed through open or reversed
sides. This is an inference from the distances; I did not trace each cover to a rebuilt face. Strict rule: a rebuilt side may
cover only faces that are 0 % visible, and these were visible in BEFORE.

### Sidewalk B (`CHTM_2nd_to_3rd_building_sidewalk_outside`)

Counts: 25,413 of 91,154 samples fail: **uv 16,833**, covered 8,118, side 398, deleted 59, overlaid 5. 25 sites, 20 with crops. No Validator note.

Crops opened (BEFORE | AFTER; sites 1 to 7 and 9):

1. **Site 1** (15,078 samples; 7,943 uv, 7,127 covered). A top-left block: BEFORE a ragged mosaic of purple and grey; AFTER the
   purple left block remains and the grey right part is clean. Purple left in AFTER means faces still seen from behind.
2. **Site 2** (9,547 samples). BEFORE: purple strip down the left third, ragged; AFTER: all grey.
3. **Site 3** (653 covered, a thin light band): BEFORE tiny purple hatching at its right end; AFTER none. The covered samples
   cannot be seen in a look-coloured crop.
4. **Site 4** (482 uv): a sloped panel. BEFORE mostly purple with grey strips (flicker); AFTER one clean grey panel.
5. **Site 5** (243 samples). A sloped surface with purple and grey patches; AFTER merged into one light grey and a violet block at the top right.
6. **Site 6** (85 covered). A large wall: BEFORE purple and grey fragments around a black patch at the bottom; AFTER a large
   violet block lower left.
7. **Site 7** (74 samples): thin edge-on slab, purple bits in BEFORE, cleaner AFTER.
8. **Site 9** (68 covered). BEFORE: a purple patch on a slab end; AFTER: none, and a grey box hangs lower than the slab: new
   geometry in front of what BEFORE showed.

Independent check: of 300 sampled UV failures, 299 have a single BEFORE layer and 292 of those do not match in UV: real
changes. The three materials (`ltstone_-3`, `-5`, `-8`) are 16 x 16 textures with a standard deviation of 2 to 3 grey
levels: almost flat. Of 400 sampled covered points, 312 and 370 (along and against the normal) meet an AFTER face 8 to 390 in away (median 39 and 60 in), facing the viewer in 100 %.

## False alarms

I found no Validator false alarm worth the name: the deletions are confirmed by a second method; the flicker-pair look
failures are the Validator doing what v0 specifies (no allowed classes). Two things are for the controller and owner
to decide, not bugs:

1. **UV on near-flat textures.** The sidewalks' 23,000 UV failures are all on 16 x 16 textures with a standard
   deviation of 2 to 3 grey levels, and 79 % of CHTM 5th's are about 1.4 texels. The rule as written counts them.
   Whether a UV tolerance that depends on the texture's contrast is wanted is the owner's call; I did not change it.
2. **The look-coloured crops cannot show a UV or a cover.** Evidence for those is the counts and the sample analysis above.
   A crop mode that colours by UV offset would make them visible (a possible P2 or evidence improvement).

## What P2's engines must fix, or show with a picture

- Do not delete a layer that BEFORE showed in a different look (CHTM 5th: 21,242 samples); cut it (E5) or ask the owner.
- Keep a face's UV within one texel unless a whole tile moves, when it merges (all three units).
- Do not leave an opening in a rebuilt side that covers visible faces (cover: A 3,199, B 9,183, CHTM 5th 4,806 samples).
- The back-seen faces that are left (side: 27, 464, 398) are faces the winding fix did not reach.
- The fix opens borders (CHTM 5th open edges 346 to 1,921; A 250 to 378).
