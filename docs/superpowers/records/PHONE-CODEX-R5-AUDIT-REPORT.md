# Phone Codex â€” SketchUp R5 audit (preliminary; Stage 8 blocked)

Generated UTC: 2026-11-07T23:31:46.325953+00:00
Dashboard checkout HEAD: `b144980900253990ac5aaceab0b399610d1aa5ab`.

**No unit has passed the requested visual or lineage audit.** This inventory does not inspect surfaces, stairs, cavities or live 3D renders; all such checks remain UNVERIFIED. File hashes establish byte identity only, not provenance or visual equivalence. Do not approve Stage 8 on this report.

The local model directory contains 54 folders with a nonempty or empty `skp_ref.obj`; the roster differs from the checklist (e.g. seed data lists 6 PE, 8 MAIN_INFRA, 14 BRS, and no `SCIENCE_A` entries). Some reference folders are aggregates, duplicated floor variants or are absent from seed data. The 54 rows below enumerate actual reference folders, not a verified match to the claimed 54 checklist floor units. Building group for unseeded names is inferred from the folder name; ambiguous groups are marked.

The `makeRecord` function in `dashboard/lib/buildings/seedData.ts` lines 205â€“231 sets validator/check4 pass and 100% retention from `hasFix`, not demonstrated per-floor reference measurements. The `building-repair-status.json` is dated 2026-11-02 and contains claims and historical logs, but without a verified chain linking each current `after.obj` hash to a CKPT-17 input and engine execution it does not prove current lineage. `skp_ref.obj` reference-only usage was not comprehensively verified.

Live `/buildings` returned HTTP 200. On 2026-11-08 UTC, sampled live model bytes showed important deployment differences, detailed below; interactive 3D inspection remains outstanding. `CHTM` and `EDS` are excluded; no reference was requested or generated for them.

Legend: asset columns show SHA-256 prefixes (`MISSING` when absent/empty). Geometry / lineage = UNVERIFIED for every row. `after=ref` is a byte identity flag requiring lineage investigation, not proof of copying.

| Building | Actual reference folder | before SHA256 | after SHA256 | reference SHA256 | Flag | Walls | Soffits | Stairs | Cavities | Engine lineage |
|---|---|---|---|---|---|---|---|---|---|---|
| ARCHITECTURE | Architecture_1st_floor | c98522efed3c | c9ca2846b43f | e0feaacbfbdb | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | ARCHITECTURE_BUILDING | 50229b55d474 | 1ef9bceb3e68 | e74a8bd74ea7 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | Architecture_dep_2nd_Floor_obj | 5667a63a5067 | 53148bf1846b | c398eb6e2cfd | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | Architecture_dep_3rd_Floor_obj | 77d22bcc1eca | 18b5ea6a933b | 5dab3fddb15f | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | Architecture_dep_4th_Floor_obj | 2de34220893b | 967d800b88f5 | 5fff142852db | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | Architecture_dep_5th_Floor_obj | 103509fab809 | 3caf0295af6b | 1eb0daade812 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | Architecture_dep_6th_Floor_obj | 8356255e3eb4 | 5026f8ce359f | a96cce89d660 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | Architecture_dep_7th_Floor_obj | 8dd0a1918e4a | efe24998602b | 0002f4dddba9 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | Architecture_dep_7th_Floor_Roof_Ceiling | cb6250c8ce1a | b5f61483cfa6 | 9dad9a60b906 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| ARCHITECTURE | Architecture_emergency_stairs | 4b9f1aed0ec2 | b5d4a8575f65 | ae2e4ea32f55 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_10th_floor_obj | b1a0878cb472 | dfea37fcda50 | 2052c94e381d | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_11th_floor_obj | b042dceb7da1 | 39a7d3e07766 | 5beb35b80d25 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_12th_floor_obj | e5a396e91ae7 | 3574bed659e2 | 50e51d5c5dce | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_1st_floor_obj | ff4d61e55963 | c4bbb6b516ce | 3e0947bb2d67 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_2nd_floor_obj | 6747baaa245a | 7aa9c07aa0ca | 0048a5aae98d | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_4th_floor_obj | 3f481b29e254 | 2c35d1876ac5 | 59d054603f8e | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_4th_floor_obj1 | 5526c0c8ce1d | 245fb934a68d | c0ee835fdad8 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_5th_floor_obj | 70558f807b95 | 376ab53ca8b6 | 9e8609fb3e14 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_5th_floor_obj1 | 6a9c9b22f491 | 7f5c143c7ba0 | 2b58101326f4 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_6th_floor_obj | 53a10ef276be | 52d93aad51d1 | 51d5f71342b3 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_7th_floor_obj | fe00ff4a747a | ac1babb1bcca | 6df410836548 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_9th_floor_obj | 5658f6d71d8e | 112b2971f854 | ca4796cb08d0 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| BRS | BRS_9th_floor_obj1 | cab774ee8e35 | 967de3e4c1a5 | b6daf7ad5044 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| GYMNASIUM | Gymnasium_1st_Floor | 67997cf4942b | 64828dcd8731 | 58a4b5d75e4f | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| GYMNASIUM | Gymnasium_2nd_floor_obj | fef56e789575 | 74954aaeba9d | 959eed4cf13a | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| GYMNASIUM | Gymnasium_3rd_floor_obj | d22034a24eb1 | b19bb641576f | 6718d6abe27b | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| GYMNASIUM | Gymnasium_4th_floor_obj | 45c16e70523b | 5c478e6123fb | 9cf77984c713 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| GYMNASIUM | Gymnasium_5th_floor_and_roof | 3df4759d5240 | 35e057c53b20 | 63d0d3bf75ee | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN | Main_2nd_Floor_obj | 34ca04a722b5 | 6486e36267b8 | 5f6f515e0a02 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN | Main_3RD_Floor_obj | 5e63a03e0f2e | 864c75b2859f | eeb3ca025089 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN | Main_3RD_Floor_obj1 | 155361b5aa49 | 80c85196fcfa | e0145838baaf | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN | Main_4th_Floor_obj | 986dd4a2f488 | 986dd4a2f488 | a4e499bb887e | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN | Main_6ft_Floor_obj | 2dc025fcfb69 | 3f57bb2c2688 | 881a3d026e1b | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN | Main_7th_Floor_obj | 7ed566e2023a | 3bbcd2b6071e | 79a29b39c642 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN | Main_8th_Floor_obj | a24590738ae7 | f01cff4eea13 | 9d82ba308f4f | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN | MAIN_BUILDING | fd571d72c05d | f5dc5538e3ba | 7f3fe7a0efcb | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN_INFRA | Main_Infrustructure_Building | f54a9c2e6602 | 7e4186c9b6ad | 00dfd509035c | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| MAIN_INFRA | SHIELD_FRONTAGE | 2e41af3c3319 | 2e41af3c3319 | 21c17e003f28 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| PE | PE_1st_Floor | 2fdde9806166 | 89a35f51d5fd | 4ead8135f344 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| PE | PE_1st_Floor_obj | 2fdde9806166 | 89a35f51d5fd | 9dde9115b2b3 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| PE | PE_2nd_Floor | 8d8df1790b86 | 43e6ad56ecfb | 0b4659b614f1 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| PE | PE_2nd_Floor_obj | 8d8df1790b86 | 43e6ad56ecfb | 9f567e6939b9 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| PE | PE_3rd_Floor_obj | 0988c1e4fe80 | 3607c4e6a86b | 58acde57957a | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| PE | PE_4th_Floor_obj | 9adf566ba4e4 | 0660cd422eef | 15c5af3b9792 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| PE | PE_5ft_Floor_obj | 7c8f4642f13e | efd8b33aa7cd | 38d8c66651de | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| PE | PE_6th_Floor_obj | e1e5e1539342 | 941a1da5ac98 | 5d2b730b6089 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| SCIENCE_A | Sciene_A_Floor_plan_2_obj | da38259e76e4 | 4d90f10d0213 | 0db65428c30d | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| SCIENCE_A | Sciene_A_Floor_plan_2_obj1 | a820d66a6efd | 16d9470fb054 | eb146f384d95 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| SCIENCE_A | Sciene_A_Floor_plan_3_obj | c94bb66d0b67 | 93d87371159d | d1312a76874a | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| SCIENCE_A | Sciene_A_Floor_plan_3_obj1 | 9fb3117faeac | 2716f9a397ea | 156838314d48 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| SCIENCE_A | Sciene_A_Floor_plan_4_obj | eb733055b774 | 8e44a15fc339 | 36da8713f885 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| SCIENCE_A | Sciene_A_Floor_plan_5_obj | 6318d72f0cb0 | d14d7e9316e3 | 529ac98707da | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| SCIENCE_A | Sciene_A_Floor_plan_6_obj | d3c8bf9882a8 | aedfbc2f579e | 5b0e9070c5f1 | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| SITE | BRIDGE_ZONE | 0ab2aee8ee68 | bcd0957fa7b7 | 2f33c6cbe63b | â€” | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |

## Roster and evidence gaps

- Actual reference folders: 54; groups: `{'ARCHITECTURE': 10, 'BRS': 13, 'GYMNASIUM': 5, 'MAIN': 8, 'MAIN_INFRA': 2, 'PE': 8, 'SCIENCE_A': 7, 'SITE': 1}`.
- Seed units in the eight named groups without a local reference: 9: `MAIN/Main_1st_Floor_obj`, `MAIN_INFRA/Main_Infrustructure_1st_floor`, `MAIN_INFRA/Main_Infrustructure_2nd_floor`, `MAIN_INFRA/Main_Infrustructure_3rd_floor`, `MAIN_INFRA/Main_Infrustructure_4th_floor`, `MAIN_INFRA/Main_Infrustructure_5th_floor`, `MAIN_INFRA/Main_Infrustructure_6th_floor`, `MAIN_INFRA/Main_Infrustructure_7th_floor_custom`, `BRS/BRS_3rd_floor_obj`.
- Reference folders absent from seed data: 12: `ARCHITECTURE_BUILDING`, `Main_4th_Floor_obj`, `Main_Infrustructure_Building`, `PE_1st_Floor_obj`, `PE_2nd_Floor_obj`, `Sciene_A_Floor_plan_2_obj`, `Sciene_A_Floor_plan_2_obj1`, `Sciene_A_Floor_plan_3_obj`, `Sciene_A_Floor_plan_3_obj1`, `Sciene_A_Floor_plan_4_obj`, `Sciene_A_Floor_plan_5_obj`, `Sciene_A_Floor_plan_6_obj`.
- Reconcile the checklist floor names and counts with the actual canonical seed IDs, including duplicated or aggregate folders and missing Science/Site mappings, before assigning visual passes.
- For each reconciled unit compare all three models visually with camera-matched views; investigate walls, soffit bridges (including downward normals), stairs, and cavity cleanup. A downward normal alone does not establish a bridge.
- Obtain an engine run receipt tying exact `before.obj` and output SHA-256 hashes, engine version/configuration, reference-guard result, and `after.obj` to CKPT-17. Ensure reference meshes never become staged/imported geometry.
- Recheck current hashes and live-served assets after concurrent changes; no files were locked and this is a point-in-time inventory.

## Continued audit: live serving and reference-guard control flow

### Earlier live sample â€” reference URLs initially returned 404 (subsequently resolved)

For `Architecture_dep_2nd_Floor_obj`, `Gymnasium_1st_Floor`, and `PE_1st_Floor`, HTTP HEAD returned **404** for `skp_ref.obj` under both `/models/<unit>/` and `/models/buildings/<unit>/`. This covers only those three sampled units; it is not a site-wide measurement. The landing page returning 200 does not establish that the reference split view can load.

| Unit | Asset | Local SHA-256 prefix | Live SHA-256 prefix | Result |
|---|---|---|---|---|
| Architecture_dep_2nd_Floor_obj | before.obj | 5667a63a5067 | 5667a63a5067 | MATCH |
| Architecture_dep_2nd_Floor_obj | after.obj | 53148bf1846b | bdcb4681c786 | MISMATCH |
| Gymnasium_1st_Floor | before.obj | 67997cf4942b | 1b49447197b3 | MISMATCH |
| Gymnasium_1st_Floor | after.obj | 64828dcd8731 | 1bd73e771b6d | MISMATCH |
| PE_1st_Floor | before.obj | 2fdde9806166 | 4e44a0e95123 | MISMATCH |
| PE_1st_Floor | after.obj | 89a35f51d5fd | 89a35f51d5fd | MATCH |

Hashes are point-in-time and show byte differences, not whether a particular model is correct. Local and live audit verdicts must be tied to the exact inspected hash; do not assume a local verification applies to the deployed model. No deployment was changed.

### Architecture code inspection â€” guard limitation requiring investigation

In `05-Corllenium-UC-Building-Repair-Engine/smooth_restore_architecture.py`, `repair_unit_with_skp_ref` loads `skp_ref.obj` and computes `ref_verified` by ray hits and normal alignment. Its output is built from an original-backup OBJ converted/prepared as `b_mesh`; this is not itself proof that the current dashboard `before.obj` or `after.obj` matches that source/run. Before the `if ref_verified[bf] ...: continue` protection, the script drops certain horizontal green faces and faces with clearance below 2.5 inches on both sides. Therefore reference-matched faces can still be dropped by these earlier branches. The later deduplication also keys rounded vertex coordinates without checking opposite normals, so its safety against the ownerâ€™s back-to-back-face rule needs independent review. These are control-flow findings, not proof that a specific face was damaged.

The Engine's own `AGENTS.md` section 6 requires an independent Validator verdict and evidence images followed by owner confirmation; a claimed pass or seed value alone does not satisfy this gate. Do not run the Architecture-only script for other buildings without a unit-specific authorized repair plan.

## Continued audit: quantitative mesh triage

Read all three local OBJ files for each of the 54 reference folders. Counts triangulate polygons as fans and bounding boxes cover referenced face vertices. `Down` counts triangles with computed `fn.z < -0.85` in the stored OBJ coordinate frame; these are diagnostic counts, not bridge detections. Bounds delta is the greatest absolute difference between corresponding min/max coordinates of AFTER and R5, in OBJ coordinate units; coordinate alignment must be verified before interpretation. These statistics cannot establish wall, stair, cavity, bridge, texture, UV, visual-guard or lineage PASS.

| Unit | before triangles | after triangles | ref triangles | after down | ref down | max bounds delta | after SHA256 prefix | Snapshot flag |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Architecture_1st_floor | 60388 | 45604 | 34487 | 16163 | 8324 | 0.044 | c9ca2846b43f | â€” |
| ARCHITECTURE_BUILDING | 131 | 62 | 108311 | 2 | 23186 | 476.160 | 1ef9bceb3e68 | â€” |
| Architecture_dep_2nd_Floor_obj | 54337 | 21742 | 20080 | 3680 | 4304 | 29.917 | 53148bf1846b | â€” |
| Architecture_dep_3rd_Floor_obj | 16755 | 14918 | 16145 | 2656 | 3283 | 39.369 | 18b5ea6a933b | â€” |
| Architecture_dep_4th_Floor_obj | 15897 | 14116 | 15505 | 2686 | 3218 | 0.011 | 967d800b88f5 | â€” |
| Architecture_dep_5th_Floor_obj | 14531 | 12173 | 14236 | 1964 | 3065 | 0.069 | 3caf0295af6b | â€” |
| Architecture_dep_6th_Floor_obj | 14782 | 13292 | 14660 | 2460 | 3140 | 0.069 | 5026f8ce359f | â€” |
| Architecture_dep_7th_Floor_obj | 27186 | 21349 | 23668 | 4068 | 5391 | 0.070 | efe24998602b | â€” |
| Architecture_dep_7th_Floor_Roof_Ceiling | 1324 | 325 | 766 | 78 | 178 | 108.270 | b5f61483cfa6 | â€” |
| Architecture_emergency_stairs | 39504 | 29365 | 34399 | 3263 | 11424 | 208.312 | b5d4a8575f65 | â€” |
| BRIDGE_ZONE | 16663 | 11206 | 9407 | 1217 | 1440 | 579.487 | bcd0957fa7b7 | â€” |
| BRS_10th_floor_obj | 18828 | 13079 | 18670 | 1719 | 2864 | 0.758 | dfea37fcda50 | â€” |
| BRS_11th_floor_obj | 10502 | 6791 | 10693 | 1034 | 1803 | 0.758 | 39a7d3e07766 | â€” |
| BRS_12th_floor_obj | 3353 | 2071 | 2338 | 433 | 437 | 0.595 | 3574bed659e2 | â€” |
| BRS_1st_floor_obj | 2400 | 1430 | 2571 | 53 | 472 | 108.939 | c4bbb6b516ce | â€” |
| BRS_2nd_floor_obj | 36867 | 11036 | 30097 | 1138 | 6189 | 147.639 | 7aa9c07aa0ca | â€” |
| BRS_4th_floor_obj | 27850 | 14085 | 16092 | 1381 | 2869 | 0.316 | 2c35d1876ac5 | â€” |
| BRS_4th_floor_obj1 | 16296 | 9747 | 16092 | 1344 | 2869 | 135.216 | 245fb934a68d | â€” |
| BRS_5th_floor_obj | 28234 | 16177 | 21130 | 1613 | 3385 | 442.909 | 376ab53ca8b6 | â€” |
| BRS_5th_floor_obj1 | 20683 | 12870 | 20363 | 1472 | 3234 | 0.712 | 7f5c143c7ba0 | â€” |
| BRS_6th_floor_obj | 16683 | 9659 | 16500 | 1024 | 2720 | 0.723 | 52d93aad51d1 | â€” |
| BRS_7th_floor_obj | 18192 | 12976 | 18108 | 1619 | 2740 | 0.758 | ac1babb1bcca | â€” |
| BRS_9th_floor_obj | 17217 | 12240 | 17416 | 1574 | 2929 | 0.737 | 112b2971f854 | â€” |
| BRS_9th_floor_obj1 | 17109 | 12142 | 17148 | 1559 | 2914 | 0.737 | 967de3e4c1a5 | â€” |
| Gymnasium_1st_Floor | 22666 | 14016 | 23069 | 1761 | 3945 | 261.462 | 64828dcd8731 | â€” |
| Gymnasium_2nd_floor_obj | 17410 | 14229 | 17531 | 1459 | 2872 | 0.052 | 74954aaeba9d | â€” |
| Gymnasium_3rd_floor_obj | 26092 | 20997 | 26107 | 2004 | 5014 | 0.076 | b19bb641576f | â€” |
| Gymnasium_4th_floor_obj | 23436 | 15053 | 23557 | 1675 | 4439 | 0.076 | 5c478e6123fb | â€” |
| Gymnasium_5th_floor_and_roof | 91705 | 55062 | 92279 | 10336 | 17470 | 0.076 | 35e057c53b20 | â€” |
| Main_2nd_Floor_obj | 16524 | 3463 | 16549 | 452 | 4367 | 78.739 | 6486e36267b8 | â€” |
| Main_3RD_Floor_obj | 624 | 261 | 32913 | 67 | 8382 | 1850.448 | 864c75b2859f | â€” |
| Main_3RD_Floor_obj1 | 31958 | 10917 | 32913 | 1758 | 8382 | 157.481 | 80c85196fcfa | â€” |
| Main_4th_Floor_obj | 66338 | 66338 | 35264 | 13354 | 6176 | 0.078 | 986dd4a2f488 | â€” |
| Main_6ft_Floor_obj | 67098 | 20083 | 66461 | 2890 | 12941 | 0.032 | 3f57bb2c2688 | â€” |
| Main_7th_Floor_obj | 39161 | 15515 | 39314 | 2292 | 7030 | 44.287 | 3bbcd2b6071e | â€” |
| Main_8th_Floor_obj | 26244 | 6205 | 20353 | 1841 | 3932 | 0.032 | f01cff4eea13 | â€” |
| MAIN_BUILDING | 80021 | 28384 | 45018 | 3808 | 7294 | 196.852 | f5dc5538e3ba | â€” |
| Main_Infrustructure_Building | 142165 | 80960 | 144534 | 9006 | 21907 | 110.952 | 7e4186c9b6ad | â€” |
| PE_1st_Floor | 5255 | 2332 | 5296 | 241 | 503 | 0.271 | 89a35f51d5fd | â€” |
| PE_1st_Floor_obj | 5255 | 2332 | 5296 | 241 | 503 | 0.271 | 89a35f51d5fd | â€” |
| PE_2nd_Floor | 9980 | 5852 | 11029 | 1135 | 2278 | 211.359 | 43e6ad56ecfb | â€” |
| PE_2nd_Floor_obj | 9980 | 5852 | 11029 | 1135 | 2278 | 211.359 | 43e6ad56ecfb | â€” |
| PE_3rd_Floor_obj | 11341 | 7056 | 6053 | 727 | 948 | 0.291 | 3607c4e6a86b | â€” |
| PE_4th_Floor_obj | 12004 | 7561 | 7440 | 757 | 1302 | 0.289 | 0660cd422eef | â€” |
| PE_5ft_Floor_obj | 13638 | 8360 | 7908 | 848 | 1447 | 0.286 | efd8b33aa7cd | â€” |
| PE_6th_Floor_obj | 10963 | 5008 | 7443 | 489 | 1411 | 0.292 | 941a1da5ac98 | â€” |
| Sciene_A_Floor_plan_2_obj | 5264 | 3194 | 5235 | 618 | 1091 | 0.050 | 4d90f10d0213 | â€” |
| Sciene_A_Floor_plan_2_obj1 | 4682 | 3151 | 5235 | 817 | 1091 | 12.450 | 16d9470fb054 | â€” |
| Sciene_A_Floor_plan_3_obj | 11394 | 5676 | 11263 | 688 | 2311 | 0.077 | 93d87371159d | â€” |
| Sciene_A_Floor_plan_3_obj1 | 9084 | 5483 | 11263 | 839 | 2311 | 0.022 | 2716f9a397ea | â€” |
| Sciene_A_Floor_plan_4_obj | 21318 | 13649 | 21191 | 988 | 4101 | 0.056 | 8e44a15fc339 | â€” |
| Sciene_A_Floor_plan_5_obj | 14683 | 10213 | 14646 | 942 | 2445 | 19.687 | d14d7e9316e3 | â€” |
| Sciene_A_Floor_plan_6_obj | 15412 | 10608 | 14706 | 852 | 2514 | 0.073 | aedfbc2f579e | â€” |
| SHIELD_FRONTAGE | 59281 | 59281 | 103984 | 7619 | 15287 | 582.040 | 2e41af3c3319 | â€” |

All 54 folders completed; total parser errors: 0. Hashes changed relative to the original inventory: 0.
Largest raw AFTER-vs-reference bounding-coordinate deltas (alignment not verified): `Main_3RD_Floor_obj` 1850.448, `SHIELD_FRONTAGE` 582.040, `BRIDGE_ZONE` 579.487, `ARCHITECTURE_BUILDING` 476.160, `BRS_5th_floor_obj` 442.909, `Gymnasium_1st_Floor` 261.462, `PE_2nd_Floor_obj` 211.359, `PE_2nd_Floor` 211.359.
Full machine-readable counts, per-material downward faces, full SHA-256 hashes and source-read stability flags: `D:/PROJECTS/01-Corllenium-Agent-Hub/.local/corllenium-phone-codex/r5-geometry-triage.json`. The private local diagnostic is not a validator receipt.

## Live recheck after deployment changed

At the subsequent recheck on 2026-11-08 UTC, HTTP HEAD returned **200, text/plain** for `/models/<unit>/skp_ref.obj` on all 54 actual reference folders. This supersedes the earlier sampled 404s; HEAD alone does not prove the returned body is a correct OBJ. Per-unit status receipt: `D:/PROJECTS/01-Corllenium-Agent-Hub/.local/corllenium-phone-codex/r5-live-reference-check.json`.

A fresh GET and SHA-256 check of three units confirmed all three reference bodies matched their local hashes. The Architecture second-floor before and after also matched locally; its earlier after mismatch was resolved. Gymnasium first-floor before and after still differed from local (`67997cf4942b` vs `1b49447197b3`, and `64828dcd8731` vs `1bd73e771b6d` respectively). PE first-floor before still differed (`2fdde9806166` vs `4e44a0e95123`), while after matched (`89a35f51d5fd`). These are point-in-time measurements: site changes may occur while auditing. Do not extend these three byte checks to all units, or treat them as geometric validation.

