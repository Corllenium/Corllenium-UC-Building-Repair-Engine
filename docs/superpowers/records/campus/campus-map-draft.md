# Campus map draft (P0-10): buildings, levels and units for the owner to confirm

Built by `python -m engine.cli campus-inventory` from the frozen CHECKPOINT-17 split snapshots (85 files, 1,766,906 triangles; clean OBJ sha256 `c1020bcf41f0503f`). **Nothing here is confirmed:** every unit has `confirmed_by_owner: false`. The machine-readable twin is `data/campus/campus_map.draft.json` (git-ignored; the command regenerates it). Heights are inches, Z up.

## What you confirm

1. Each building's **level table** (base, top, slab) in the tables below.
2. Each **flag**: which group of a duplicate pair stays, whether a misnamed group is renamed or its level is accepted, whether a missing level is real, which building a group of another footprint belongs to, and each proposed split.

Coverage: every one of the 85 splits is in exactly one unit (81) or exactly one split proposal (4); the units hold 1,766,906 of 1,766,906 triangles (ok).

## Summary

| Building | Groups | Triangles | Levels | Floor units | Element units | Flags |
|---|---|---|---|---|---|---|
| ARCHITECTURE | 9 | 244,634 | 7 | 7 | 1 | 1 |
| BRS | 16 | 258,859 | 12 | 12 | 1 | 4 |
| CHTM | 13 | 197,082 | 11 | 11 | 1 | 2 |
| EDS | 11 | 303,673 | 11 | 11 | 0 | 0 |
| GYMNASIUM | 5 | 181,318 | 5 | 5 | 0 | 0 |
| MAIN | 8 | 262,599 | 8 | 8 | 0 | 3 |
| MAIN_INFRA | 2 | 148,026 | 4 | 4 | 0 | 2 |
| PE | 7 | 64,136 | 6 | 6 | 0 | 0 |
| SCIENCE_A | 7 | 81,872 | 5 | 5 | 0 | 6 |
| SITE | 7 | 24,707 |  |  |  |  |

Flags in total: duplicate 3, misnamed 2, missing 4, shared 2, footprint 3, split 4.

## Levels and floor units

### ARCHITECTURE

9 groups. Level numbers count from the lowest band (7 of 7 named floor groups agree).

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L01 | ARCHITECTURE-L01 | 1,189.0 | 1,385.8 | 1,189.0 - 1,228.3 | 60,491 | Architecture_1st_floor (60,388), ARCHITECTURE_BUILDING (103, band 1) |
| L02 | ARCHITECTURE-L02 | 1,385.8 | 1,582.7 | 1,385.8 - 1,425.2 | 54,343 | Architecture_dep_2nd_Floor_obj (54,343) |
| L03 | ARCHITECTURE-L03 | 1,582.7 | 1,799.2 | 1,582.7 - 1,622.0 | 16,783 | Architecture_dep_3rd_Floor_obj (16,755), ARCHITECTURE_BUILDING (28, band 3) |
| L04 | ARCHITECTURE-L04 | 1,799.2 | 1,976.4 | 1,799.2 - 1,818.9 | 15,897 | Architecture_dep_4th_Floor_obj (15,897) |
| L05 | ARCHITECTURE-L05 | 1,976.4 | 2,173.2 | 1,976.4 - 2,015.8 | 14,531 | Architecture_dep_5th_Floor_obj (14,531) |
| L06 | ARCHITECTURE-L06 | 2,173.2 | 2,370.1 | 2,173.2 - 2,212.6 | 14,782 | Architecture_dep_6th_Floor_obj (14,782) |
| L07 | ARCHITECTURE-L07 | 2,370.1 | 2,692.3 | 2,370.1 - 2,409.4 | 28,280 | Architecture_dep_7th_Floor_obj (28,280) |

### BRS

16 groups. Level numbers count from the lowest band (13 of 14 named floor groups agree).

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L01 | BRS-L01 | 1,267.7 | 1,503.9 | no slab found | 2,400 | BRS_1st_floor_obj (2,400) |
| L02 | BRS-L02 | 1,503.9 | 1,700.8 | 1,503.9 - 1,543.3 | 36,867 | BRS_2nd_floor_obj (36,867) |
| L03 | BRS-L03 | 1,700.8 | 1,897.6 | 1,700.8 - 1,740.2 | 22,017 | BRS_3rd_floor_obj (22,017) |
| L04 | BRS-L04 | 1,897.6 | 2,133.9 | 1,897.6 - 1,937.0 | 44,179 | BRS_4th_floor_obj (27,850), BRS_4th_floor_obj1 (16,329) |
| L05 | BRS-L05 | 2,133.9 | 2,330.7 | 2,133.9 - 2,173.2 | 48,917 | BRS_5th_floor_obj (28,234), BRS_5th_floor_obj1 (20,683) |
| L06 | BRS-L06 | 2,330.7 | 2,527.6 | 2,330.7 - 2,370.1 | 16,683 | BRS_6th_floor_obj (16,683) |
| L07 | BRS-L07 | 2,527.6 | 2,724.4 | 2,527.6 - 2,566.9 | 18,192 | BRS_7th_floor_obj (18,192) |
| L08 | BRS-L08 | 2,724.4 | 2,921.3 | 2,724.4 - 2,763.8 | 17,109 | BRS_9th_floor_obj1 (17,109) |
| L09 | BRS-L09 | 2,921.3 | 3,118.1 | 2,921.3 - 2,960.6 | 17,217 | BRS_9th_floor_obj (17,217) |
| L10 | BRS-L10 | 3,118.1 | 3,315.0 | 3,118.1 - 3,157.5 | 18,828 | BRS_10th_floor_obj (18,828) |
| L11 | BRS-L11 | 3,315.0 | 3,541.3 | 3,315.0 - 3,354.3 | 10,502 | BRS_11th_floor_obj (10,502) |
| L12 | BRS-L12 | 3,541.3 | 3,810.6 | 3,541.3 - 3,551.2 | 5,715 | BRS_12th_floor_obj (3,357), BRS_ZONE (2,358) |

### CHTM

13 groups. Level numbers count from the lowest band (11 of 12 named floor groups agree).

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L01 | CHTM-L01 | 1,385.8 | 1,582.7 | 1,385.8 - 1,425.2 | 7,856 | CHTM_1st_floor_zone (7,856) |
| L02 | CHTM-L02 | 1,582.7 | 1,779.5 | 1,582.7 - 1,622.0 | 18,074 | Chtm_2nd_floor (18,074) |
| L03 | CHTM-L03 | 1,779.5 | 1,976.4 | 1,779.5 - 1,818.9 | 22,793 | CHTM_3rd_floor (22,793) |
| L04 | CHTM-L04 | 1,976.4 | 2,173.2 | 1,976.4 - 2,015.8 | 18,188 | CHTM_4th_floor (18,188) |
| L05 | CHTM-L05 | 2,173.2 | 2,360.2 | 2,173.2 - 2,212.6 | 20,599 | chtm_5ft_floor (20,599) |
| L06 | CHTM-L06 | 2,360.2 | 2,527.6 | 2,360.2 - 2,370.1 | 15,698 | CHTM_6ft_floor_obj (15,698) |
| L07 | CHTM-L07 | 2,527.6 | 2,724.4 | 2,527.6 - 2,566.9 | 17,039 | CHTM_7th_floor_obj (17,039) |
| L08 | CHTM-L08 | 2,724.4 | 2,921.3 | 2,724.4 - 2,763.8 | 16,762 | CHTM_8th_floor_obj (16,762) |
| L09 | CHTM-L09 | 2,921.3 | 3,118.1 | 2,921.3 - 2,960.6 | 15,957 | CHTM_9th_floor_obj (15,957) |
| L10 | CHTM-L10 | 3,118.1 | 3,315.0 | 3,118.1 - 3,157.5 | 14,934 | CHTM_10th_floor_obj (14,934) |
| L11 | CHTM-L11 | 3,315.0 | 3,718.5 | 3,315.0 - 3,354.3 | 20,589 | CHTM_11th_floor_obj (13,925), CHTM_12th_floor_obj (6,664) |

### EDS

11 groups. Level numbers count from the lowest band (11 of 11 named floor groups agree).

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L01 | EDS-L01 | 1,543.3 | 1,700.8 | 1,543.3 - 1,563.0 | 12,764 | EDS_1st_Floor (12,764) |
| L02 | EDS-L02 | 1,700.8 | 1,897.6 | 1,700.8 - 1,740.2 | 17,700 | Eds_2nd_Floor_obj (17,700) |
| L03 | EDS-L03 | 1,897.6 | 2,133.9 | 1,897.6 - 1,937.0 | 47,710 | EDS_3rd_Floor (47,710) |
| L04 | EDS-L04 | 2,133.9 | 2,330.7 | 2,133.9 - 2,173.2 | 40,921 | EDS_4th_Floor (40,921) |
| L05 | EDS-L05 | 2,330.7 | 2,527.6 | 2,330.7 - 2,370.1 | 27,401 | Eds_5ft_Floor_obj (27,401) |
| L06 | EDS-L06 | 2,527.6 | 2,724.4 | 2,527.6 - 2,566.9 | 29,524 | Eds_6th_Floor_obj (29,524) |
| L07 | EDS-L07 | 2,724.4 | 2,921.3 | 2,724.4 - 2,763.8 | 29,050 | Eds_7th_Floor_obj (29,050) |
| L08 | EDS-L08 | 2,921.3 | 3,118.1 | 2,921.3 - 2,960.6 | 30,798 | Eds_8th_Floor_obj (30,798) |
| L09 | EDS-L09 | 3,118.1 | 3,315.0 | 3,118.1 - 3,157.5 | 34,979 | Eds_9th_Floor_obj (34,979) |
| L10 | EDS-L10 | 3,315.0 | 3,511.8 | 3,315.0 - 3,354.3 | 23,822 | Eds_10th_Floor_obj (23,822) |
| L11 | EDS-L11 | 3,511.8 | 3,738.2 | 3,511.8 - 3,551.2 | 9,004 | Eds_11th_Floor_obj (9,004) |

### GYMNASIUM

5 groups. Level numbers count from the lowest band (5 of 5 named floor groups agree).

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L01 | GYMNASIUM-L01 | 1,189.0 | 1,385.8 | 1,189.0 - 1,228.3 | 22,666 | Gymnasium_1st_Floor (22,666) |
| L02 | GYMNASIUM-L02 | 1,385.8 | 1,612.2 | 1,385.8 - 1,425.2 | 17,410 | Gymnasium_2nd_floor_obj (17,410) |
| L03 | GYMNASIUM-L03 | 1,612.2 | 1,799.2 | 1,612.2 - 1,622.0 | 26,092 | Gymnasium_3rd_floor_obj (26,092) |
| L04 | GYMNASIUM-L04 | 1,799.2 | 1,976.4 | 1,799.2 - 1,818.9 | 23,436 | Gymnasium_4th_floor_obj (23,436) |
| L05 | GYMNASIUM-L05 | 1,976.4 | 2,645.7 | 1,976.4 - 2,015.8 | 91,714 | Gymnasium_5th_floor_and_roof (91,714) |

### MAIN

8 groups. Level numbers count from the lowest band (7 of 7 named floor groups agree).

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L01 | MAIN-L01 | 1,346.5 | 1,503.9 | no slab found | 1,395 | Main_1st_Floor_obj (1,395) |
| L02 | MAIN-L02 | 1,503.9 | 1,700.8 | 1,503.9 - 1,543.3 | 16,530 | Main_2nd_Floor_obj (16,530) |
| L03 | MAIN-L03 | 1,700.8 | 1,897.6 | 1,700.8 - 1,740.2 | 32,606 | Main_3RD_Floor_obj1 (31,979), Main_3RD_Floor_obj (627) |
| L04 | MAIN-L04 | 1,897.6 | 2,094.5 | 1,897.6 - 1,937.0 | 34,548 | MAIN_BUILDING (34,548, band 4) |
| L05 | MAIN-L05 | 2,094.5 | 2,291.3 | 2,094.5 - 2,133.9 | 45,530 | MAIN_BUILDING (45,530, band 5) |
| L06 | MAIN-L06 | 2,291.3 | 2,488.2 | 2,291.3 - 2,330.7 | 67,113 | Main_6ft_Floor_obj (67,113) |
| L07 | MAIN-L07 | 2,488.2 | 2,665.3 | 2,488.2 - 2,527.6 | 39,167 | Main_7th_Floor_obj (39,167) |
| L08 | MAIN-L08 | 2,665.3 | 3,078.7 | 2,665.3 - 2,685.0 | 25,710 | Main_8th_Floor_obj (25,710) |

### MAIN_INFRA

2 groups. Level numbers count from the lowest band (1 of 1 named floor groups agree).

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L01 | MAIN_INFRA-L01 | 1,189.0 | 1,503.9 | 1,189.0 - 1,228.3 | 5,792 | Main_Infrustructure_1st_floor (5,792) |
| L02 | MAIN_INFRA-L02 | 1,503.9 | 1,700.8 | 1,503.9 - 1,543.3 | 40,106 | Main_Infrustructure_Building (40,106, band 2) |
| L03 | MAIN_INFRA-L03 | 1,700.8 | 2,389.8 | 1,700.8 - 1,740.2 | 74,638 | Main_Infrustructure_Building (74,638, band 3) |
| L04 | MAIN_INFRA-L04 | 2,389.8 | 2,645.7 | 2,389.8 - 2,409.4 | 27,490 | Main_Infrustructure_Building (27,490, band 4) |

### PE

7 groups. Level numbers count from the lowest band (6 of 6 named floor groups agree).

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L01 | PE-L01 | 1,385.8 | 1,582.7 | 1,385.8 - 1,425.2 | 5,255 | PE_1st_Floor (5,255) |
| L02 | PE-L02 | 1,582.7 | 1,799.2 | 1,582.7 - 1,622.0 | 10,935 | PE_2nd_Floor (9,980), PE_GROUND_landscaping (955) |
| L03 | PE-L03 | 1,799.2 | 1,976.4 | 1,799.2 - 1,818.9 | 11,341 | PE_3rd_Floor_obj (11,341) |
| L04 | PE-L04 | 1,976.4 | 2,192.9 | 1,976.4 - 2,015.8 | 12,004 | PE_4th_Floor_obj (12,004) |
| L05 | PE-L05 | 2,192.9 | 2,370.1 | 2,192.9 - 2,212.6 | 13,638 | PE_5ft_Floor_obj (13,638) |
| L06 | PE-L06 | 2,370.1 | 2,687.3 | 2,370.1 - 2,409.4 | 10,963 | PE_6th_Floor_obj (10,963) |

### SCIENCE_A

7 groups. Level numbers start at L02: 6 of 6 named floor groups agree on an offset of +1.

| Level | Unit | Base | Top | Slab bottom - top | Triangles | Groups (triangles) |
|---|---|---|---|---|---|---|
| L02 | SCIENCE_A-L02 | 1,503.9 | 1,661.4 | 1,503.9 - 1,543.3 | 9,946 | Sciene_A_Floor_plan_2_obj (5,264), Sciene_A_Floor_plan_2_obj1 (4,682) |
| L03 | SCIENCE_A-L03 | 1,661.4 | 1,858.3 | 1,661.4 - 1,681.1 | 20,478 | Sciene_A_Floor_plan_3_obj (11,394), Sciene_A_Floor_plan_3_obj1 (9,084) |
| L04 | SCIENCE_A-L04 | 1,858.3 | 1,996.1 | 1,858.3 - 1,912.4 | 16,252 | Sciene_A_Floor_plan_4_obj (16,252, band 4) |
| L05 | SCIENCE_A-L05 | 1,996.1 | 2,291.3 | 1,996.1 - 2,020.7 | 19,749 | Sciene_A_Floor_plan_4_obj (5,066, band 5), Sciene_A_Floor_plan_5_obj (14,683) |
| L06 | SCIENCE_A-L06 | 2,291.3 | 2,645.7 | 2,291.3 - 2,330.7 | 15,447 | Sciene_A_Floor_plan_6_obj (15,447) |

## Element and site units

| Unit | Type | Triangles | Lowest z | Highest z | Spans | Group |
|---|---|---|---|---|---|---|
| ARCHITECTURE-E-Architecture_emergency_stairs | element | 39,527 | 1,544.9 | 2,444.4 | L03, L04 | Architecture_emergency_stairs |
| BRS-E-BRS_GROUND_FLOOR_PATHWAY_obj | element | 233 | 1,425.2 | 1,543.3 | L01, L02 | BRS_GROUND_FLOOR_PATHWAY_obj |
| CHTM-E-CHTM_sidewalk_zone | element | 8,593 | 1,582.7 | 2,114.2 | L03, L04 | CHTM_sidewalk_zone |
| SITE-BRIDGE_ZONE | site | 16,663 | 1,425.2 | 2,541.6 |  | BRIDGE_ZONE |
| SITE-Group124 | site | 30 | 1,425.2 | 1,425.2 |  | Group124 |
| SITE-Group137 | site | 2,898 | 1,340.2 | 1,678.2 |  | Group137 |
| SITE-Group220 | site | 199 | 1,425.2 | 2,448.8 |  | Group220 |
| SITE-ROAD_harrison_front | site | 2,334 | 1,533.5 | 1,681.1 |  | ROAD_harrison_front |
| SITE-Side_walk_harrision_Main_building_2 | site | 405 | 1,228.3 | 1,425.2 |  | Side_walk_harrision_Main_building_2 |
| SITE-unnamed | site | 2,178 | 1,425.2 | 3,718.5 |  | unnamed |

## Proposed splits (by face centre; no triangle is cut)

| Group | Level | Triangles | Share | Faces with z from | to (exclusive) |
|---|---|---|---|---|---|
| ARCHITECTURE_BUILDING | L01 | 103 | 79 % | -inf | 1,581.7 |
|  | L03 | 28 | 21 % | 1,581.7 | +inf |
| MAIN_BUILDING | L04 | 34,548 | 43 % | -inf | 2,093.5 |
|  | L05 | 45,530 | 57 % | 2,093.5 | +inf |
| Main_Infrustructure_Building | L02 | 40,106 | 28 % | -inf | 1,699.8 |
|  | L03 | 74,638 | 52 % | 1,699.8 | 2,388.8 |
|  | L04 | 27,490 | 19 % | 2,388.8 | +inf |
| Sciene_A_Floor_plan_4_obj | L04 | 16,252 | 76 % | -inf | 1,995.1 |
|  | L05 | 5,066 | 24 % | 1,995.1 | +inf |

## Flags

### Duplicates (Jaccard similarity of the face fingerprints, flagged from 0.25)

| Building | Group A | Group B | Similarity | Exact at print step | Faces A / B | Shared | Of the smaller | Kind |
|---|---|---|---|---|---|---|---|---|
| BRS | BRS_5th_floor_obj | BRS_5th_floor_obj1 | 39.2 % | 0.0 % | 28,234 / 20,683 | 13,787 | 66.7 % | shifted |
| SCIENCE_A | Sciene_A_Floor_plan_3_obj | Sciene_A_Floor_plan_3_obj1 | 79.6 % | 0.0 % | 11,392 / 9,083 | 9,073 | 99.9 % | shifted |
| SCIENCE_A | Sciene_A_Floor_plan_2_obj | Sciene_A_Floor_plan_2_obj1 | 80.3 % | 0.0 % | 5,264 / 4,682 | 4,431 | 94.6 % | shifted |

### Misnamed (the floor number in the name against the level its faces sit in)

| Group | Name says | Sits in | Level z (base - top) | Building |
|---|---|---|---|---|
| BRS_9th_floor_obj1 | 9 | L08 | 2,724.4 - 2,921.3 | BRS |
| CHTM_12th_floor_obj | 12 | L11 | 3,315.0 - 3,718.5 | CHTM |

### Missing levels (a floor number below the highest named one that no group is named for)

| Building | Level | Held by |
|---|---|---|
| BRS | L08 | BRS_9th_floor_obj1 |
| MAIN | L04 | MAIN_BUILDING |
| MAIN | L05 | MAIN_BUILDING |
| SCIENCE_A | L01 | nothing: no group, no band |

### Levels shared by groups named for different floors (a level may be missing there)

| Building | Level | Floors named | Groups |
|---|---|---|---|
| CHTM | L11 | 11, 12 | CHTM_11th_floor_obj, CHTM_12th_floor_obj |
| SCIENCE_A | L05 | 4, 5 | Sciene_A_Floor_plan_4_obj, Sciene_A_Floor_plan_5_obj |

### Footprints (a group whose box lies mostly in another building)

| Group | Named for | In its own building | In | That building's footprint |
|---|---|---|---|---|
| Main_Infrustructure_1st_floor | MAIN_INFRA | 97 % | SCIENCE_A | 100 % |
| BRS_GROUND_FLOOR_PATHWAY_obj | BRS | 72 % | PE | 79 % |
| Sciene_A_Floor_plan_6_obj | SCIENCE_A | 78 % | MAIN_INFRA | 91 % |

## How the draft was made

1. **Level table**, per building: area histograms of up-facing (`n_z > 0.9`) and down-facing (`n_z < -0.9`) triangles over z in 1 in bins. A peak is a local maximum of at least 15 % of the largest; peaks within 20 in merge, the strongest staying. A slab is an up-facing peak (its top) with a down-facing peak (its bottom, the level's `base`) below it.
2. **Bands and units**: a band runs from one base to the next; a face is in a band by its centre z. A group's *parts* are the fewest bands holding 80 % of its triangles. One part is a floor unit; several parts make an element unit when the name holds stair, bridge, roof, zone, shell, ground, pathway or road, and a split proposal otherwise. A band no floor group occupies is dropped. Groups without a building prefix are site units.
3. **Numbering**: from the lowest band (L01), unless a strict majority of the named floor groups agree on a positive offset (Science A: floors 2 to 6), which then starts the numbers and leaves the lower levels missing.
4. **Flags**: duplicates by fingerprint (a face is its three vertices sorted, its winding and its look key, so a back-to-back pair never matches); misnamed by the number in the name against the level; missing by the floor numbers the names skip; footprints by the XY boxes.

Constants where CHECKPOINT-17 showed the brief's value cannot work (measured on the frozen data):

| Constant | Brief | Used | Measured reason |
|---|---|---|---|
| slab bottom window | 24 in | 60 in | slabs are 19.7 in (half a block), 39.4 in (a block) or, for Science A plan_4, 54 in thick |
| slab bottom pick | nearest down peak | lowest down peak in the window | stepped slabs have a second underside about 30 in above the real bottom (BRS 5th, EDS 3rd) |
| levels closer than | 20 in (peak merge only) | 100 in | terraces and thin layers repeat every 39 in; the shortest storey measured is 157 in |
| duplicate vertex identity | the print step | print step and 0.5 in | the obj1 copies sit 0.03 in (Science A) to 0.4 in (BRS 4th, 5th) off their originals, so nothing coincides at the print step |

Levels per building with the brief's constants (what the draft would otherwise have): ARCHITECTURE 4, BRS 3, CHTM 2, EDS 2, GYMNASIUM 3, MAIN 2, MAIN_INFRA 2, PE 5, SCIENCE_A 5.
