# SDK cross-check: the CHECKPOINT-17 export against its backup

Run 2026-10-04T09:03:40+08:00. Backup `UC-campus-FIXED-v2026-07-11 - CHECKPOINT-17.skp` (sha256 `ddecd020a826`, read through a verified copy), export frozen in `source.json` of 2026-10-03T19:12:52+08:00 (85 files).
Tolerance: bounding box 0.2 in (twice the export's print step of 0.1 in, measured on its largest coordinate 24244.2), area 0.5 %.

| result | files |
|---|---:|
| match | 65 |
| mismatch | 20 |
| ambiguous | 0 |
| miss | 0 |

Ambiguous: a file that matches some of several groups of one name but not others, so its verdict depends on a pairing the shapes cannot settle. Miss: no group of that name in the backup.

- 11 files were paired with their group by shape, because the name does not say which is which
- 4 files were decided without a pairing, because their verdict is the same whichever group of their name they go with: 2 match every group (`any_group`), 2 match none and are shown against the nearest (`nearest_group`)
- the SketchUp walk saw 1,329 groups, 153 instances and 705,109 faces in 36.224 s (peak 2526.0 MB of commit); left out as hidden: 0 groups or instances and 0 faces, and as on a tag that is off: 0 and 0
- the export holds 1,766,906 triangles in 85 files; 42,791 of them have no area, the print step having collapsed them to a line
- bounding boxes of the 85 paired files differ by at most 12.478 in (median 0.032 in; the tolerance is 0.2 in)
- triangles of the paired files (a face of v corners and h holes counts v + 2h - 2): the backup 1,861,181, the export 1,766,906; the export has 94,275 triangles fewer (5.1 %)

## Worst mismatches (5 of 20)

| file | paired by | box, max off (in) | area: backup vs export | difference |
|---|---|---:|---|---:|
| Sciene_A_Floor_plan_2_obj1 | nearest_group | 12.478 | 5,675,640 vs 4,703,669 sq in | +20.66 % |
| Sciene_A_Floor_plan_3_obj1 | nearest_group | 0.044 | 8,750,466 vs 7,244,383 sq in | +20.79 % |
| unnamed | name | 0.048 | 6,882,009 vs 6,740,862 sq in | +2.09 % |
| BRS_9th_floor_obj1 | geometry | 0.032 | 10,444,261 vs 10,234,413 sq in | +2.05 % |
| CHTM_4th_floor | name | 0.046 | 9,964,227 vs 9,766,411 sq in | +2.03 % |

The reason for every mismatch, in words, is in `skp_check.json`. In every mismatch the backup has MORE area than the export (+0.51 % to +20.79 %).

- `Sciene_A_Floor_plan_3_obj`, several groups of one name, not paired: 2 groups of the backup are called like this and the export has 2 files for them; no pairing is close enough (every pair must be within 5 in and 5% of area); no pairing is needed for 2 of the 2 files (1 match every group, 1 match none)
- `Sciene_A_Floor_plan_2_obj`, several groups of one name, not paired: 2 groups of the backup are called like this and the export has 2 files for them; no pairing is close enough (every pair must be within 5 in and 5% of area); no pairing is needed for 2 of the 2 files (1 match every group, 1 match none)

Each export file holds the faces SketchUp's exporter gave it, and the owner's split rule decides which file that is (`engine/campus/skp_check.py`), so a file is compared with the faces that went into it, not with a whole group.
