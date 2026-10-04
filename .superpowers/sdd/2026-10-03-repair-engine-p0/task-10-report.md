# Task 10 (P0-10): the implementer's report (handed back as text, recorded by the controller) and the controller's rulings

Status: **DONE_WITH_CONCERNS.** Branch `claude/P0-10`, worktree `.claude/worktrees/P0-10`, from 478326b, worktree clean.
Raw outputs: `<session scratchpad>/p0-10/`:
- `red_item*.txt`, `green_item*.txt`, `mutation_item*.txt`;
- `real_run*.txt`, `full_suite.txt`;
- `sensitivity.txt`, `sens3.txt`, `near.txt`, `foot_literal.txt`, `agree.txt`;
- `literal/` for the brief's literal constants.

## Commits
1. 499c934 prefix table + floor number parser.
2. f98de15 level table from up/down slab area.
3. cf7cb33 floor/element/site units + split proposals.
4. 5bb6310 duplicates.
5. 82fee9e misnamed + name-anchored numbering.
6. 896c3d4 missing levels.
7. 9500782 footprint flags + coverage proof.
8. 016a4df the `campus-inventory` command.
9. dc76608 real run + shared-level flag + vertex-exact open ends + 60 in window + the committed draft table.
10. 2a86b40 module docstring.

Files:
- `engine/campus/inventory.py` (new);
- `engine/tests/test_campus_inventory.py` (new, 63 tests);
- `engine/cli.py` (+38);
- `docs/superpowers/records/campus/campus-map-draft.md` (generated).

## Tests
- Every item was red first. Where a test passed on arrival it was mutation-checked; details per item are in the raw outputs.
- Area suite: 165 passed.
- Whole engine suite: 738 passed, 1 xfailed in 593.52 s (on 478326b's base).

## Real run (31 s)
`campus inventory: 85 splits, 1,766,906 triangles -> 79 units (floor 69, element 3, site 7), 4 split proposals`

Per building:

| Building | Groups | Levels |
|---|---|---|
| ARCHITECTURE | 9 | 7 |
| BRS | 16 | 12 |
| CHTM | 13 | 11 |
| EDS | 11 | 11 |
| GYMNASIUM | 5 | 5 |
| MAIN | 8 | 8 |
| MAIN_INFRA | 2 | 4 |
| PE | 7 | 6 |
| SCIENCE_A | 7 | 5 (from L02) |

- Flags: duplicate 3, misnamed 2, missing 4, shared 2, footprint 3, split 4.
- Coverage: 81 whole + 4 split = 85 of 85 splits, and 1,766,906 of 1,766,906 triangles.
- Independent check: every member's sha256 and path ids agree, and every unit has `confirmed_by_owner: false`.
- The md is reproduced byte for byte.

## Flags
**Duplicate** (0.5 in vertex identity plus winding; Jaccard on distinct faces):

| Pair | Jaccard | Share of smaller | At the exact print step |
|---|---|---|---|
| Sciene_A plan_2 obj/obj1 | 0.803 | 94.6 % | 0 % |
| Sciene_A plan_3 obj/obj1 | 0.796 | 99.9 % | 0 % |
| BRS_5th obj/obj1 | 0.392 | 66.7 % | 0 % |

Not flagged:
- BRS_4th, a near miss at 0.175;
- BRS_9th obj/obj1, which share nothing.

**Misnamed:**
- BRS_9th_floor_obj1 is in L08;
- CHTM_12th_floor_obj is in L11 (L12 is not detected).

**Missing:**
- BRS L08, held by BRS_9th_obj1;
- MAIN L04 and L05, held by MAIN_BUILDING's parts;
- SCIENCE_A L01, held by nothing.

**Shared** (the implementer's addition):
- CHTM L11 holds groups named 11 and 12;
- SCIENCE_A L05 holds groups named 4 and 5.

**Footprint:**
- Main_Infrustructure_1st_floor: 100 % in SCIENCE_A;
- BRS_GROUND_FLOOR_PATHWAY: 79 % in PE, against 72 % in its own building;
- Sciene_A plan_6: 91 % in MAIN_INFRA, against 78 % in its own.

**Split:**
- MAIN_BUILDING: L04 43 %, L05 57 %;
- Main_Infrustructure_Building: L02 28 %, L03 52 %, L04 19 %;
- Sciene_A plan_4: L04 76 %, L05 24 %;
- ARCHITECTURE_BUILDING (131 tris): 79 % and 21 %.

## Known cases
| Case | Result |
|---|---|
| BRS_9th_obj1 → L08 | appears |
| Science A duplicates ~90 % | appear as "shifted" copies (obj1 about 0.03 in off); 0 % with the exact print-step fingerprint |
| MAIN_BUILDING into 2 | appears |
| Main_Infrustructure_Building into 7 | **NOT met**: 3 parts; at most 4 under every setting measured. Its slab planes are two interleaved series, and no principled rule picks 7 |
| Science A L01 missing | appears |

## Departures from the brief, all measured
The brief's constants as written break the real tables: BRS gets 3 levels, CHTM 2, and there are 48 misnamed flags. Slabs are 19.7, 39.4 or 54 in thick.
1. Slab-bottom window 24 → 60 in.
2. Base = the lowest down peak in the window.
3. Levels closer than 100 in collapse (the shortest storey is 157.5 in).
4. A slab top with no bottom is not a slab.
5. Duplicates:
   - vertex identity is the print step + 0.5 in, for identity only;
   - winding is in the fingerprint, so opposite pairs never match;
   - each flag gives both the exact and the tolerant numbers.
6. Units and bands:
   - a group's parts are the fewest bands holding 80 % of its triangles;
   - bands no floor occupies are dropped;
   - the ground band exists only if a floor group is mostly in it;
   - elements make no level;
   - numbering is anchored by names;
   - "missing" is name-based;
   - the shared flag is new.
7. The prefix match is case-insensitive, with an underscore or the end of the name after it.

## Doubts
- A split member lists the whole group's path ids; the part is selected by `z_range`.
- The weak tables are SCIENCE_A (a spurious base at 1996; plan_5's real base 2094.5 is undetected) and MAIN_INFRA.
- The CHTM L12 slab is single-sided (its top is 3 % of the largest up peak).
- Process: item 5's commit was chained after an area-suite run. Its own green had been read in the previous call.

## Controller's rulings (2026-10-04)
- **The 0.5 in vertex identity in the duplicate measure: ALLOWED.**
  - It is a read-only comparison key. No geometry is welded or written, so it is not §4's "weld above 0.1 mm".
  - It is named and measured, with the exact and tolerant numbers both reported.
  - No fix engine may reuse it to merge vertices.
  - It goes into the P0-13 sheet for the owner's view. Cost if wrong: the owner reads the exact numbers instead.
- **Constants changed from the brief: ACCEPTED.** The brief's values were guesses; the implementer measured them on the real data. Every change is commented in `InventoryParams` and listed in the md.
- **"Main_Infra into 7" not met: ACCEPTED as a draft.**
  - `campus_map` is owner-confirmed by design (`confirmed_by_owner: false`).
  - The 3-part proposal and the interleaved slab series go to the P0-13 decision sheet, along with CHTM L12, SCIENCE_A L05/L01, and the weak MAIN_INFRA and SCIENCE_A tables.
- The chained commit: noted; no history rewrite.
