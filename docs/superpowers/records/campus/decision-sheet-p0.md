# Owner decision sheet: P0, the campus before any fix (2026-10-04)

Everything below was measured from CHECKPOINT-17, read only through the frozen export
(`data/campus/source.json`: 85 split files, 1,766,906 triangles). Sources:
- the inventory `campus-map-draft.md` (P0-10);
- the census `census.md` (P0-12; every floor's error map);
- the SketchUp check `skp-check.md` (P0-11);
- the material looks (P0-09).

Each question shows Claude's proposal and, after the owner answers, **the answer**.

## 1. Floors per building (the level table)
| Building | Levels | Base heights, in (L01 first) |
|---|---|---|
| ARCHITECTURE | 7 | 1189, 1386, 1583, 1799, 1976, 2173, 2370 |
| BRS | 12 | 1268, 1504, 1701, 1898, 2134, 2331, 2528, 2724, 2921, 3118, 3315, 3541 |
| CHTM | 11 | 1386, 1583, 1780, 1976, 2173, 2360, 2528, 2724, 2921, 3118, 3315 |
| EDS | 11 | 1543, 1701, 1898, 2134, 2331, 2528, 2724, 2921, 3118, 3315, 3512 |
| GYMNASIUM | 5 | 1189, 1386, 1612, 1799, 1976 |
| MAIN | 8 | 1346, 1504, 1701, 1898, 2094, 2291, 2488, 2665 |
| MAIN_INFRA | 4 | 1189, 1504, 1701, 2390 |
| PE | 6 | 1386, 1583, 1799, 1976, 2193, 2370 |
| SCIENCE_A | 5, numbered L02-L06 | 1504, 1661, 1858, 1996, 2291 |

The inventory gives 79 units: 69 floors, 3 elements (stairs and pathways spanning floors) and 7 site pieces. Every one of
the 85 files is covered.

## 2. Files that hold several floors (proposed splits by face centre; no triangle is cut)
- MAIN_BUILDING: L04 (43 %) and L05 (57 %).
- Main_Infrustructure_Building: L02 (28 %), L03 (52 %), L04 (19 %). **3 floors, not 7:** its slab planes form two
  interleaved series, and no principled rule finds 7.
- Sciene_A_Floor_plan_4_obj: L04 (76 %), L05 (24 %).
- ARCHITECTURE_BUILDING (131 triangles): L01 and L03.

## 3. Duplicate copies
| Pair | Shared faces | Note |
|---|---|---|
| Sciene_A_Floor_plan_2_obj / _obj1 | 95 % of the smaller (Jaccard 0.80) | _obj1 sits ~0.03 in from _obj, so the two flicker. The SketchUp check finds _obj1 ~17 % short of the backup and 12.5 in off; _obj matches the backup (+0.05 %) |
| Sciene_A_Floor_plan_3_obj / _obj1 | 100 % of the smaller (Jaccard 0.80) | the same picture; _obj1 ~17 % short; _obj matches (+0.03 %) |
| BRS_5th_floor_obj / _obj1 | 67 % of the smaller (Jaccard 0.39) | a partial copy |

Not duplicates: BRS_9th_floor_obj and _obj1 share no faces (_obj1 is really floor 8), and BRS_4th shares only 18 %.
The duplicate measure counts vertices within 0.5 in of each other as one. That is a read-only comparison: no geometry is
changed, and nothing is welded.

## 4. Misnamed and missing floors
- BRS_9th_floor_obj1 sits in L08, the floor below its name. BRS has no group named floor 8.
- CHTM_12th_floor_obj sits in L11 together with CHTM_11th. Its slab is single-sided, so no separate L12 was detected.
- MAIN L04 and L05 are held only by MAIN_BUILDING's two parts.
- SCIENCE_A has no L01. The footprint check puts Main_Infrustructure_1st_floor 100 % inside Science A.

## 5. Identical-look materials (tint groups)
The 391 materials have only 97 distinct looks (texture + colour + opacity). 58 looks are shared by 352 materials; for
example 21 `minecraft_concrete_white_-N` materials are one texture. A flicker pair of two such materials looks the same
from both layers.

**Proposal:** same look = one material for E4. The duplicate layer is removed, and is not cut as a different-look pair (E5).

## 6. The targets for check 2 ("the problems are solved"), per error kind
The census totals for all 85 floors are counted in faces; E4/E5 are pairs, by look.

| Kind | Campus total | Proposed target after the fix |
|---|---|---|
| Flicker, same look (E4) | 341,131 pairs | 0 |
| Flicker, different look (E5) | 514,573 pairs | 0; ties the rules cannot settle go to the owner |
| Reversed faces (E2) | 44,560 | 0 |
| Hidden faces (E3) | 890,048 | 0, except protected faces (side meshes, room surfaces seen from inside) |
| Zero-area and stray bits (E1) | 45,656 | zero-area 0; visible debris is kept and listed with a picture |
| Cracks / T-junctions (E6) | 285,638 | 0 |
| Open edges / holes (E8) | 39,531 | listed: narrow flat fills done, the rest go to "needs modelling" |

## 7. The export against the CHECKPOINT-17 backup (SketchUp check)
- 65 files match. 20 differ in face area only, always with the backup larger, by +0.51 % to +2.09 % on 18 files and
  +20.7 % on the two Science A _obj1 copies.
- The export lacks 94,275 triangles (5.1 %). Most are exact duplicate faces stacked in the backup.
- Five files stay unexplained after removing duplicates: unnamed +2.09 %, EDS 1st +0.71 %, CHTM 4th +0.77 %,
  BRIDGE_ZONE +0.72 %, MAIN_BUILDING +0.57 %.

**Proposal:** keep the export as the repair source. Look at the five unexplained files with pictures before their
floors are fixed.

## 8. Answers
(filled in from the owner's replies)
