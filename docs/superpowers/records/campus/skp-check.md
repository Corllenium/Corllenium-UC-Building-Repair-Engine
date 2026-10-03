# SDK cross-check: the CHECKPOINT-17 export against its backup

Run 2026-10-03T20:38:26+08:00. Backup `UC-campus-FIXED-v2026-07-11 - CHECKPOINT-17.skp` (sha256 `ddecd020a826`, read through a verified copy), export frozen in `source.json` of 2026-10-03T19:12:52+08:00 (85 files).
Tolerance: bounding box 0.2 in (twice the export's print step of 0.1 in, measured on its largest coordinate 24244.2), area 0.5 %.

| result | files |
|---|---:|
| match | 63 |
| mismatch | 18 |
| ambiguous | 4 |
| miss | 0 |

Ambiguous: several groups or files of one name that their shapes could not tell apart. Miss: no group of that name in the backup.

- 11 files were paired with their group by shape, because the name does not say which is which
- the SketchUp walk saw 1,329 groups, 153 instances and 705,109 faces in 46.101 s (peak 2526.1 MB of commit); left out as hidden: 0 groups or instances and 0 faces, and as on a tag that is off: 0 and 0
- bounding boxes of the 81 paired files differ by at most 0.05 in (median 0.032 in; the tolerance is 0.2 in)
- triangles of the paired files (a face of v corners and h holes counts v + 2h - 2): the backup 1,826,873, the export 1,736,482; the export has 90,391 triangles fewer (4.9 %)

## Worst mismatches (5 of 18)

| file | paired by | box, max off (in) | area: backup vs export | difference |
|---|---|---:|---|---:|
| unnamed | name | 0.048 | 6,882,009 vs 6,740,862 sq in | +2.09 % |
| BRS_9th_floor_obj1 | geometry | 0.032 | 10,444,261 vs 10,234,413 sq in | +2.05 % |
| CHTM_4th_floor | name | 0.046 | 9,964,227 vs 9,766,411 sq in | +2.03 % |
| BRS_9th_floor_obj | geometry | 0.032 | 10,881,591 vs 10,672,705 sq in | +1.96 % |
| CHTM_3rd_floor | name | 0.042 | 12,813,355 vs 12,579,329 sq in | +1.86 % |

The reason for every mismatch, in words, is in `skp_check.json`. In every mismatch the backup has MORE area than the export (+0.51 % to +2.09 %).

- ambiguous `Sciene_A_Floor_plan_3_obj` (Sciene_A_Floor_plan_3_obj, Sciene_A_Floor_plan_3_obj1): 2 groups of the backup are called like this and the export has 2 files for them; no pairing is close enough (every pair must be within 5 in and 5% of area)
- ambiguous `Sciene_A_Floor_plan_2_obj` (Sciene_A_Floor_plan_2_obj, Sciene_A_Floor_plan_2_obj1): 2 groups of the backup are called like this and the export has 2 files for them; no pairing is close enough (every pair must be within 5 in and 5% of area)

Each export file holds the faces SketchUp's exporter gave it, and the owner's split rule decides which file that is (`engine/campus/skp_check.py`), so a file is compared with the faces that went into it, not with a whole group.
