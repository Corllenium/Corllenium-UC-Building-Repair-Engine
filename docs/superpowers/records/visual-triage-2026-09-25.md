# Visual Triage Inspection Report (2026-09-25)

## Overview & Scope
Visual inspection of 84 renders across two SketchUp models fixed by UC MODEL FIXER engine (git commit ca463c2 / post-brief 03 side-rebuild merge):
1. **Model A (`CHTM_SIDE_WALK_2nd_floor`)**:
   - `data/visual_triage/2026-09-25/A-skp-render/` (21 images via SketchUp C API read-back)
   - `data/visual_triage/2026-09-25/CHTM_SIDE_WALK_2nd_floor-qa/` (21 images via engine QA sheet)
2. **Model B (`CHTM_2nd_to_3rd_building_sidewalk_outside`)**:
   - `data/visual_triage/2026-09-25/B-skp-render/` (21 images via SketchUp C API read-back)
   - `data/visual_triage/2026-09-25/CHTM_2nd_to_3rd_building_sidewalk_outside-qa/` (21 images via engine QA sheet)

Defect Categories Inspected:
- (1) Hole or see-through gap in a surface
- (2) Face showing its back side (blue-purple tint in SketchUp / reversed face exposure)
- (3) Line drawn inside a flat surface that is not an edge of the model
- (4) Jagged, sawtooth, or stepped slab side / underside
- (5) Floating or loose piece
- (6) Slab that looks hollow like a tray from below
- (7) Anything else that would look wrong to a person checking the model in SketchUp

---

## Part 1: File A — SketchUp API Renders (`A-skp-render/`)

### 1. `A-skp-render/bottom.png`
- **Location**: Far left outer margin of the big landing (x ≈ 2673.2)
  - **Defect**: Dense rectangular and irregular line clutter and boxes drawn inside the flat bottom surface. [Category 3]
  - **Certainty**: sure
- **Location**: Center and upper-left of the big landing
  - **Defect**: Long straight radial lines cutting inward across the flat bottom surface. [Category 3]
  - **Certainty**: sure
- **Location**: Lower-right angled edge of the big landing
  - **Defect**: Sawtooth / jagged stepped perimeter with triangular shard lines cutting into the underside. [Category 4, 3]
  - **Certainty**: sure
- **Location**: Lower center of the big landing
  - **Defect**: Floating small triangular line fragment / speck on the underside. [Category 5]
  - **Certainty**: likely
- **Location**: Center walkway bridge connection
  - **Defect**: Stepped transverse seam line at the bridge bend. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Right side (lower landing underside)
  - **Defect**: Prominent stepped terraced contour lines running across the underside flat surface. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Lower edge of lower landing
  - **Defect**: Triangular shards and jagged edge contour lines. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Far right edge
  - **Defect**: Long see-through vertical slot / gap separating the outer curb block from the main lower landing slab. [Category 1]
  - **Certainty**: sure

### 2. `A-skp-render/chunk0_bottom.png`
- **Location**: Center and right across lower landing underside
  - **Defect**: Terraced, stepped contour lines running across the bottom surface (regions resolved at different elevations / incomplete bottom). [Category 3, 4, 6]
  - **Certainty**: sure
- **Location**: Lower-right near the ramp junction
  - **Defect**: Ragged cluster of triangular shards and jagged lines. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Far left (top-left in view)
  - **Defect**: Deep vertical gap / slot completely separating the curb block from the landing slab. [Category 1]
  - **Certainty**: sure
- **Location**: Far right at walkway ramp underside
  - **Defect**: Stepped notch / drop-off on the walkway underside. [Category 4]
  - **Certainty**: sure

### 3. `A-skp-render/chunk0_side.png`
- **Location**: Foreground left
  - **Defect**: Long detached curb block separated from the landing slab behind it by an open gap. [Category 1, 5]
  - **Certainty**: sure
- **Location**: Under the lower landing slab (behind curb)
  - **Defect**: Multi-tiered / staggered horizontal layers hanging at slightly different depths under the slab. [Category 4, 7]
  - **Certainty**: sure

### 4. `A-skp-render/chunk0_top.png`
- **Location**: Center of lower landing (sloped section)
  - **Defect**: Diagonal row of step lines across the sloped surface. [Category 3]
  - **Certainty**: sure
- **Location**: Inner curved corner where walkway ramp meets lower landing
  - **Defect**: Notched seam and small crack lines at the curved junction. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Far left
  - **Defect**: Continuous see-through slot / gap separating the curb block from the landing. [Category 1]
  - **Certainty**: sure
- **Location**: Far right (walkway ramp connection)
  - **Defect**: Transverse seam line across the walkway. [Category 3]
  - **Certainty**: sure

### 5. `A-skp-render/chunk1_bottom.png`
- **Location**: Lower-left at walkway ramp connection to lower landing
  - **Defect**: Stepped notch / vertical drop transition on the walkway underside. [Category 4]
  - **Certainty**: sure
- **Location**: Far right (edge of big landing underside)
  - **Defect**: Triangular lines and shard fragments cutting into the big slab underside. [Category 3, 5]
  - **Certainty**: sure

### 6. `A-skp-render/chunk1_side.png`
- **Location**: Center walkway bridge
  - **Defect**: Transverse seam line at the bend. [Category 3]
  - **Certainty**: sure
- **Location**: Lower left (under lower landing)
  - **Defect**: Vertical seam lines and staggered horizontal layers under the slab edge. [Category 3, 4, 7]
  - **Certainty**: sure

### 7. `A-skp-render/chunk1_top.png`
- **Location**: Center of the connecting walkway bridge
  - **Defect**: Transverse seam line cutting across the walkway. [Category 3]
  - **Certainty**: sure
- **Location**: Upper-right junction with big landing
  - **Defect**: Transverse seam line at the slab connection. [Category 3]
  - **Certainty**: sure
- **Location**: Upper perimeter edge of the walkway
  - **Defect**: Small notch / stepped irregularity on the edge line. [Category 4]
  - **Certainty**: sure
- **Location**: Lower-left junction with lower landing
  - **Defect**: Seam line and step line. [Category 3]
  - **Certainty**: sure

### 8. `A-skp-render/chunk2_bottom.png`
- **Location**: Center and left of the big landing underside
  - **Defect**: Long straight radial lines cutting across the flat bottom surface. [Category 3]
  - **Certainty**: sure
- **Location**: Right margin of the big landing underside (x ≈ 2673.2)
  - **Defect**: Dense rectangular line clutter and internal boxes inside flat surface. [Category 3]
  - **Certainty**: sure
- **Location**: Top-right and bottom-right edges
  - **Defect**: Jagged triangular shards, stepped teeth, and fragmented lines along the perimeter. [Category 4, 3]
  - **Certainty**: sure
- **Location**: Bottom corner
  - **Defect**: Isolated triangular line fragment / speck. [Category 5]
  - **Certainty**: likely

### 9. `A-skp-render/chunk2_side.png`
- **Location**: Upper edge / rim of the big landing
  - **Defect**: Jagged, notched sawtooth irregularities along the top perimeter edge. [Category 4]
  - **Certainty**: sure
- **Location**: Flat top surface
  - **Defect**: Grazing lines visible across the surface. [Category 3]
  - **Certainty**: sure
- **Location**: Bottom side profile
  - **Defect**: Stepped underside profile with uneven thickness. [Category 4, 7]
  - **Certainty**: sure

### 10. `A-skp-render/chunk2_top.png`
- **Location**: Right margin of the big landing (x ≈ 2673.2)
  - **Defect**: Dense cluster of lines inside flat surface (rectangles, triangles, lines parallel to border). [Category 3]
  - **Certainty**: sure
- **Location**: Upper-left edge of the big landing
  - **Defect**: Stray line segments cutting into the flat surface. [Category 3]
  - **Certainty**: sure
- **Location**: Center of the big landing
  - **Defect**: Isolated specks / dots on the flat surface. [Category 5]
  - **Certainty**: likely

### 11. `A-skp-render/nx.png`
- **Location**: Top-right edge of the big landing
  - **Defect**: Jagged, notched sawtooth irregularities along the upper rim; internal lines on top. [Category 4, 3]
  - **Certainty**: sure
- **Location**: Bottom-right (lower landing profile)
  - **Defect**: Stepped contour lines and vertical seam lines on the side wall. [Category 4, 3]
  - **Certainty**: sure

### 12. `A-skp-render/ny.png`
- **Location**: Far left
  - **Defect**: Separated curb block with vertical see-through gap from the landing slab. [Category 1]
  - **Certainty**: sure
- **Location**: Center-left (lower landing)
  - **Defect**: Multi-tiered horizontal slab undersides hanging at staggered elevations. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Far right (big landing end wall)
  - **Defect**: Dense vertical lines / wireframe clutter on the end face. [Category 3]
  - **Certainty**: sure

### 13. `A-skp-render/obl_bot_a.png`
- **Location**: Lower-right (big landing underside)
  - **Defect**: Radial lines cutting inward, jagged triangular shards and sawtooth perimeter, rectangular line clutter on outer margin. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Center bridge underside
  - **Defect**: Stepped transition line on bridge underside. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Upper-left (lower landing underside)
  - **Defect**: Stepped terraced contour lines outlining different underside depths. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Far left
  - **Defect**: Open see-through slot separating curb block from landing. [Category 1]
  - **Certainty**: sure

### 14. `A-skp-render/obl_bot_b.png`
- **Location**: Upper area (big landing underside)
  - **Defect**: Radial lines converging across bottom surface; dense line clutter along left margin. [Category 3]
  - **Certainty**: sure
- **Location**: Lower area (lower landing underside)
  - **Defect**: Stepped terraced contour lines on bottom surface; ragged triangle shards at corner. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Bottom-right
  - **Defect**: Open gap separating curb block from landing slab. [Category 1]
  - **Certainty**: sure

### 15. `A-skp-render/obl_top_a.png`
- **Location**: Upper-right (big landing)
  - **Defect**: Dense cluster of internal rectangular, triangular, and diagonal lines along the outer margin; specks in center. [Category 3, 5]
  - **Certainty**: sure
- **Location**: Center walkway bridge
  - **Defect**: Transverse seam line cutting across walkway. [Category 3]
  - **Certainty**: sure
- **Location**: Lower-left (lower landing)
  - **Defect**: Step lines across sloped surface; curved transition seam; vertical see-through slot separating outer curb block. [Category 1, 3]
  - **Certainty**: sure

### 16. `A-skp-render/obl_top_b.png`
- **Location**: Lower-right (big landing)
  - **Defect**: Jagged/sawtooth perimeter edge and internal lines along the margin. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Center
  - **Defect**: Walkway bridge seam lines. [Category 3]
  - **Certainty**: sure
- **Location**: Upper-left (lower landing)
  - **Defect**: Step lines on sloped surface; see-through slot separating outer curb block. [Category 1, 3]
  - **Certainty**: sure

### 17. `A-skp-render/px.png`
- **Location**: Right side (big landing profile)
  - **Defect**: Multi-tiered overlapping slab levels hanging at different heights. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Center-left (under lower landing)
  - **Defect**: Clutter of horizontal lines and step lines forming multiple underside slab layers. [Category 4, 7]
  - **Certainty**: sure

### 18. `A-skp-render/py.png`
- **Location**: Far left vertical face
  - **Defect**: Wireframe clutter / multiple vertical lines drawn on the end wall. [Category 3]
  - **Certainty**: sure
- **Location**: Right side (lower landing)
  - **Defect**: Step lines on landing profile; vertical gap separating end curb block. [Category 1, 4]
  - **Certainty**: sure

### 19. `A-skp-render/side_low_a.png`
- **Location**: Upper rim of big landing
  - **Defect**: Jagged sawtooth notches and small lines cutting into the upper edge. [Category 4, 3]
  - **Certainty**: sure
- **Location**: Center-left (lower landing)
  - **Defect**: Stepped side wall profile; gap to curb block. [Category 1, 4]
  - **Certainty**: sure

### 20. `A-skp-render/side_low_b.png`
- **Location**: Far left (big landing)
  - **Defect**: Low grazing angle shows stepped irregularities along the edge. [Category 4]
  - **Certainty**: likely
- **Location**: Far right (lower landing)
  - **Defect**: Stepped multi-layer underside profile and gap to curb block. [Category 1, 4]
  - **Certainty**: sure

### 21. `A-skp-render/top.png`
- **Location**: Right side (big landing, x ≈ 2673.2)
  - **Defect**: Long vertical line parallel to right border, dense network of line clutter (rectangles, triangles, stray segments) on the outer right margin. [Category 3]
  - **Certainty**: sure
- **Location**: Center-left of big landing
  - **Defect**: Isolated specks / dots inside the flat surface. [Category 5]
  - **Certainty**: likely
- **Location**: Center walkway bridge
  - **Defect**: Transverse seam line dividing straight and bent sections. [Category 3]
  - **Certainty**: sure
- **Location**: Left side (lower landing)
  - **Defect**: Step lines across sloped section; notched seam along curved inner transition. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Far left
  - **Defect**: Continuous see-through slot / gap separating rectangular curb block from lower landing slab. [Category 1]
  - **Certainty**: sure

---

## Part 2: File A — Engine QA Sheet Renders (`CHTM_SIDE_WALK_2nd_floor-qa/`)

*Note: The engine QA sheet renders polygon loop boundaries from region rings plus all triangle edges for unmerged copied-through rows. All physical model defects seen in SketchUp renders persist here, with additional unmerged triangulation diagonals drawn explicitly.*

### 22. `CHTM_SIDE_WALK_2nd_floor-qa/bottom.png`
- **Location**: Left side (big landing)
  - **Defect**: Radial lines, perimeter triangular shards, margin line clutter (x ≈ 2673.2), center triangular fragment. [Category 3, 4, 5]
  - **Certainty**: sure
- **Location**: Right side (lower landing)
  - **Defect**: Stepped underside terrace contour lines, triangular shards at ramp connection, curb gap. [Category 1, 3, 4]
  - **Certainty**: sure

### 23. `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_bottom.png`
- **Location**: Center and right (lower landing underside)
  - **Defect**: Terraced contour lines on underside; triangular shards at ramp connection; curb gap on left. [Category 1, 3, 4, 6]
  - **Certainty**: sure

### 24. `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_side.png`
- **Location**: Foreground
  - **Defect**: Curb gap, multi-tiered landing profile, plus unmerged triangulation edges visible on sloped surface. [Category 1, 3, 4, 7]
  - **Certainty**: sure

### 25. `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_top.png`
- **Location**: Lower landing surface
  - **Defect**: Prominent fan of unmerged triangulation diagonals radiating from bottom-left corner across to the curved rim (copied-through unmerged region). [Category 3]
  - **Certainty**: sure
- **Location**: Sloped landing & inner curve
  - **Defect**: Diagonal step lines, notched curved seam, curb gap on left. [Category 1, 3, 4]
  - **Certainty**: sure

### 26. `CHTM_SIDE_WALK_2nd_floor-qa/chunk1_bottom.png`
- **Location**: Walkway underside
  - **Defect**: Stepped notch at lower landing connection; triangular shard lines on big slab underside. [Category 3, 4, 5]
  - **Certainty**: sure

### 27. `CHTM_SIDE_WALK_2nd_floor-qa/chunk1_side.png`
- **Location**: Walkway and lower landing profile
  - **Defect**: Transverse seam at bend, stepped underside layers with vertical seams under lower landing. [Category 3, 4, 7]
  - **Certainty**: sure

### 28. `CHTM_SIDE_WALK_2nd_floor-qa/chunk1_top.png`
- **Location**: Walkway bridge
  - **Defect**: Transverse seam lines across walkway, notch on top perimeter edge, unmerged triangulation lines on left connection. [Category 3, 4]
  - **Certainty**: sure

### 29. `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_bottom.png`
- **Location**: Big landing underside
  - **Defect**: Long radial lines, right margin rectangular clutter, perimeter triangular shards, floating triangle fragment. [Category 3, 4, 5]
  - **Certainty**: sure

### 30. `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_side.png`
- **Location**: Big landing side profile
  - **Defect**: Jagged sawtooth top rim, grazing surface lines, stepped underside profile. [Category 3, 4]
  - **Certainty**: sure

### 31. `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_top.png`
- **Location**: Big landing top surface
  - **Defect**: Dense right margin line clutter (x ≈ 2673.2), upper edge stray lines, isolated specks in center. [Category 3, 5]
  - **Certainty**: sure

### 32. `CHTM_SIDE_WALK_2nd_floor-qa/nx.png`
- **Location**: Top rim of big landing & lower landing
  - **Defect**: Jagged sawtooth top rim, side wall steps, plus unmerged triangulation diagonals visible on lower landing face. [Category 3, 4]
  - **Certainty**: sure

### 33. `CHTM_SIDE_WALK_2nd_floor-qa/ny.png`
- **Location**: End walls and lower landing
  - **Defect**: Curb gap, multi-tiered landing profile, end wall vertical clutter, unmerged triangulation lines. [Category 1, 3, 4, 7]
  - **Certainty**: sure

### 34. `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_a.png`
- **Location**: Undersides of both landings
  - **Defect**: Radial lines on big landing, jagged perimeter shards, stepped terrace contour lines on lower landing, curb gap. [Category 1, 3, 4]
  - **Certainty**: sure

### 35. `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_b.png`
- **Location**: Underside oblique
  - **Defect**: Big landing radial lines and margin clutter; lower landing stepped terrace lines; curb gap. [Category 1, 3, 4]
  - **Certainty**: sure

### 36. `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_a.png`
- **Location**: Lower landing & big landing
  - **Defect**: Full unmerged triangulation fan across lower landing; big landing margin line clutter; curb gap. [Category 1, 3]
  - **Certainty**: sure

### 37. `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_b.png`
- **Location**: Lower landing & big landing
  - **Defect**: Triangulation fan across lower landing; big landing jagged rim and margin lines; curb gap. [Category 1, 3, 4]
  - **Certainty**: sure

### 38. `CHTM_SIDE_WALK_2nd_floor-qa/px.png`
- **Location**: Side profile
  - **Defect**: Multi-tiered slab levels, horizontal line clutter under landing, unmerged triangulation edges. [Category 3, 4, 7]
  - **Certainty**: sure

### 39. `CHTM_SIDE_WALK_2nd_floor-qa/py.png`
- **Location**: Side profile
  - **Defect**: End wall vertical wireframe clutter, curb gap, stepped landing profile, unmerged triangulation diagonals. [Category 1, 3, 4]
  - **Certainty**: sure

### 40. `CHTM_SIDE_WALK_2nd_floor-qa/side_low_a.png`
- **Location**: Grazing side view
  - **Defect**: Jagged big slab rim, curb gap, unmerged triangulation lines on lower landing. [Category 1, 3, 4]
  - **Certainty**: sure

### 41. `CHTM_SIDE_WALK_2nd_floor-qa/side_low_b.png`
- **Location**: Low side view
  - **Defect**: Stepped underside profile, curb gap, triangulation lines on landing. [Category 1, 3, 4]
  - **Certainty**: sure

### 42. `CHTM_SIDE_WALK_2nd_floor-qa/top.png`
- **Location**: Lower landing (left)
  - **Defect**: Prominent unmerged triangulation fan radiating across the landing surface from corner to curved edge. [Category 3]
  - **Certainty**: sure
- **Location**: Big landing (right, x ≈ 2673.2)
  - **Defect**: Vertical margin line and dense line clutter (rectangles, triangles, stray lines); center specks. [Category 3, 5]
  - **Certainty**: sure
- **Location**: Bridge & curb
  - **Defect**: Notch on bridge top edge, bridge transverse seam, curb see-through slot. [Category 1, 3, 4]
  - **Certainty**: sure

---

## Part 3: File B — SketchUp API Renders (`B-skp-render/`)

### 43. `B-skp-render/bottom.png`
- **Location**: Middle slabs along horizontal arm (top-center/right)
  - **Defect**: Completely hollow like an upside-down tray from below! Vertical perimeter walls enclose an empty recessed cavity with interior partition lines and no bottom floor (reveals back of top face in SketchUp). [Category 6, 1, 2]
  - **Certainty**: sure
- **Location**: Sloped ramp (lower-left in this view)
  - **Defect**: Stepped vertical fin / hanging wall hanging down below the ramp slab into open air. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Inner corner at ramp / lower landing junction
  - **Defect**: Jagged notch / tooth at inner corner. [Category 4]
  - **Certainty**: sure
- **Location**: Bottom-left corner of lower landing
  - **Defect**: Chamfered corner with internal spur line cutting into flat surface. [Category 3]
  - **Certainty**: sure

### 44. `B-skp-render/chunk0_bottom.png`
- **Location**: Right side at junction with chunk 1
  - **Defect**: Sudden vertical drop-off into the open hollow recessed tray cavity of chunk 1; missing bottom floor. [Category 6, 1]
  - **Certainty**: sure

### 45. `B-skp-render/chunk0_side.png`
- **Location**: Far-left cantilever slab
  - **Defect**: Rectangular notch / cutout on the end profile face. [Category 4]
  - **Certainty**: sure
- **Location**: Under slab on the right
  - **Defect**: Open gap leading into hollow interior cavity; internal diagonal truss/strut wireframe lines visible inside the hollow space. [Category 1, 6, 7]
  - **Certainty**: sure

### 46. `B-skp-render/chunk0_top.png`
- **Location**: Right side at junction with chunk 1
  - **Defect**: Transverse seam line across walkway and small notch at junction. [Category 3, 4]
  - **Certainty**: sure

### 47. `B-skp-render/chunk1_bottom.png`
- **Location**: Entire chunk 1 underside
  - **Defect**: Hollow tray cavity with vertical inner perimeter walls; inset stepped floor panels at different depths; perimeter cutouts/notches; diagonal interior partition lines. [Category 6, 1, 4]
  - **Certainty**: sure

### 48. `B-skp-render/chunk1_side.png`
- **Location**: Underside along walkway
  - **Defect**: Hanging skirt panels at 3-4 different depths (teeth/crenellations) hanging into empty air! [Category 4, 7]
  - **Certainty**: sure
- **Location**: Between hanging skirt panels
  - **Defect**: See-through open slots / gaps where you can see straight through the model or into the hollow interior. [Category 1]
  - **Certainty**: sure
- **Location**: Ramp connection (right side)
  - **Defect**: Sharp downward-pointing fin / tooth at the ramp connection. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Far-left underside
  - **Defect**: Internal diagonal criss-cross truss lines visible inside the open underside cavity. [Category 7]
  - **Certainty**: sure

### 49. `B-skp-render/chunk1_top.png`
- **Location**: Inner edge at ramp junction
  - **Defect**: Irregular triangular cutout / notch in the walking surface with a sharp downward-pointing fin/tooth. [Category 1, 4]
  - **Certainty**: sure
- **Location**: Outer perimeter edge
  - **Defect**: Rectangular notch cutout along the perimeter; transverse line cutting into the surface from the notch. [Category 1, 3, 4]
  - **Certainty**: sure
- **Location**: Walkway surface
  - **Defect**: Transverse seam lines across the walkway. [Category 3]
  - **Certainty**: sure

### 50. `B-skp-render/chunk2_bottom.png`
- **Location**: Sloped ramp underside (region 309)
  - **Defect**: Stepped fin / hanging wall running along the ramp edge. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Left side
  - **Defect**: Continuation of the hollow tray cavity from chunk 1. [Category 6, 1]
  - **Certainty**: sure
- **Location**: Lower landing connection
  - **Defect**: Step down and notch / tooth at inner corner. [Category 4]
  - **Certainty**: sure

### 51. `B-skp-render/chunk2_side.png`
- **Location**: Upper-left at ramp connection
  - **Defect**: Sharp downward-hanging tooth / fin projecting below the slab. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Ramp / landing connection
  - **Defect**: Small notch and line where ramp meets landing. [Category 3, 4]
  - **Certainty**: sure

### 52. `B-skp-render/chunk2_top.png`
- **Location**: Inner corner at ramp junction
  - **Defect**: Notches and teeth at the inner corner connection. [Category 4]
  - **Certainty**: sure
- **Location**: Walkway surface
  - **Defect**: Transverse seam lines dividing walkway sections. [Category 3]
  - **Certainty**: sure
- **Location**: Lower landing (far right)
  - **Defect**: Chamfered corner with internal spur line cutting into flat surface. [Category 3]
  - **Certainty**: sure

### 53. `B-skp-render/nx.png`
- **Location**: Left end under upper landing
  - **Defect**: Hollow recessed cavity / hanging skirt and downward-pointing tooth / fin. [Category 6, 4, 7]
  - **Certainty**: sure
- **Location**: Middle ramp profile
  - **Defect**: Sloped ramp profile with lines/notches at junction. [Category 3, 4]
  - **Certainty**: sure

### 54. `B-skp-render/ny.png`
- **Location**: Underside of middle slabs
  - **Defect**: Panels hanging down at 3-4 different depths like teeth/crenellations; see-through slots/gaps between hanging panels; jagged stepped fins. [Category 1, 4, 7]
  - **Certainty**: sure

### 55. `B-skp-render/obl_bot_a.png`
- **Location**: Middle slabs
  - **Defect**: Completely hollow tray! Deep recessed cavity with internal perimeter walls and partition lines, no bottom floor (reveals back of top face in SketchUp). [Category 6, 1, 2]
  - **Certainty**: sure
- **Location**: Sloped ramp
  - **Defect**: Prominent stepped fin / hanging wall underneath the ramp. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Under upper-left landing
  - **Defect**: See-through slot / gap into hollow cavity. [Category 1]
  - **Certainty**: sure
- **Location**: Ramp / landing corner
  - **Defect**: Tooth / notch at inner corner. [Category 4]
  - **Certainty**: sure

### 56. `B-skp-render/obl_bot_b.png`
- **Location**: Middle slabs
  - **Defect**: Hollow tray cavity clearly exposed from opposite angle; vertical perimeter walls and stepped interior panels. [Category 6, 1, 2]
  - **Certainty**: sure
- **Location**: Sloped ramp
  - **Defect**: Stepped fin hanging down below the ramp. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Inner rim
  - **Defect**: Hanging skirt panels at different depths with open see-through slots. [Category 1, 4, 7]
  - **Certainty**: sure

### 57. `B-skp-render/obl_top_a.png`
- **Location**: Middle slabs
  - **Defect**: Stepped skirt panels hanging at different depths visible below the walkway edge. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Inner corner at ramp junction
  - **Defect**: Notches and teeth along edge. [Category 4]
  - **Certainty**: sure
- **Location**: Left arm & lower landing
  - **Defect**: Thin slab profile, transverse seams, chamfered corner spur line. [Category 3, 7]
  - **Certainty**: sure

### 58. `B-skp-render/obl_top_b.png`
- **Location**: Middle slabs
  - **Defect**: Hanging skirt panels of varying depths along the outer rim. [Category 4, 7]
  - **Certainty**: sure
- **Location**: Ramp junction & landing
  - **Defect**: Notches and teeth at ramp junction; walkway seams; chamfered corner spur. [Category 3, 4]
  - **Certainty**: sure

### 59. `B-skp-render/px.png`
- **Location**: Top vertical arm
  - **Defect**: Vertical seam lines and notch. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Far left horizontal walkway
  - **Defect**: Slab flattens to a paper-thin / knife-edge single surface without thickness. [Category 7, 4]
  - **Certainty**: sure

### 60. `B-skp-render/py.png`
- **Location**: Walkway side profile
  - **Defect**: Slab thickness changes abruptly; stepped hanging piece under left side; lines drawn on vertical wall of middle slab. [Category 4, 3, 7]
  - **Certainty**: sure

### 61. `B-skp-render/side_low_a.png`
- **Location**: Underside of middle slabs
  - **Defect**: Grazing view shows see-through holes / openings under the slab; hanging skirt panels at uneven depths; open cavity into interior. [Category 1, 4, 6, 7]
  - **Certainty**: sure

### 62. `B-skp-render/side_low_b.png`
- **Location**: Low side profile
  - **Defect**: Stepped elevation changes and abruptly varying slab thicknesses. [Category 4, 7]
  - **Certainty**: sure

### 63. `B-skp-render/top.png`
- **Location**: Top horizontal arm
  - **Defect**: Transverse seam line between left arm and middle slab; small notches / step indentations along bottom edge of upper-left arm. [Category 3, 4]
  - **Certainty**: sure
- **Location**: Inner corner at ramp junction
  - **Defect**: Cluster of jagged notches, teeth, and small cutout lines at the inner corner. [Category 4, 1]
  - **Certainty**: sure
- **Location**: Lower landing (bottom-right)
  - **Defect**: Chamfered corner with horizontal spur line cutting into flat surface; transverse seam line at bottom of vertical walkway. [Category 3]
  - **Certainty**: sure

---

## Part 4: File B — Engine QA Sheet Renders (`CHTM_2nd_to_3rd_building_sidewalk_outside-qa/`)

*Note: The engine QA sheet renders polygon loop boundaries from region rings plus all triangle edges for unmerged copied-through rows. In Model B, the ramp (region 309) and parts of the lower landing were copied through unmerged, causing all triangulation diagonals to be drawn across the ramp.*

### 64. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/bottom.png`
- **Location**: Middle slabs
  - **Defect**: Hollow tray cavity, vertical inner walls, missing bottom floor. [Category 6, 1, 2]
  - **Certainty**: sure
- **Location**: Sloped ramp & landing
  - **Defect**: Stepped fin under sloped ramp; corner notch; chamfered corner spur line. [Category 4, 7, 3]
  - **Certainty**: sure

### 65. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk0_bottom.png`
- **Location**: Right side at junction with chunk 1
  - **Defect**: Identical to SKP render: drop-off into hollow recessed tray cavity; missing bottom floor. [Category 6, 1]
  - **Certainty**: sure

### 66. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk0_side.png`
- **Location**: Cantilever & underside
  - **Defect**: Identical to SKP render: cantilever notch, open gap to hollow cavity, internal diagonal truss lines. [Category 1, 6, 7]
  - **Certainty**: sure

### 67. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk0_top.png`
- **Location**: Walkway junction
  - **Defect**: Identical to SKP render: transverse seam at junction, small edge notch. [Category 3, 4]
  - **Certainty**: sure

### 68. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_bottom.png`
- **Location**: Chunk 1 underside
  - **Defect**: Hollow tray cavity with vertical inner walls, stepped interior floor panels, perimeter notches, diagonal partitions. [Category 6, 1, 4]
  - **Certainty**: sure

### 69. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_side.png`
- **Location**: Underside
  - **Defect**: Hanging panels at 3-4 different depths, see-through open slots between panels, downward-pointing tooth at ramp connection, internal truss lines, plus unmerged triangulation edges. [Category 1, 4, 7, 3]
  - **Certainty**: sure

### 70. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_top.png`
- **Location**: Walkway & ramp junction
  - **Defect**: Triangular notch cutout with hanging tooth, rectangular notch along perimeter with transverse line, transverse seams, plus triangulation edges. [Category 1, 3, 4]
  - **Certainty**: sure

### 71. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_bottom.png`
- **Location**: Ramp underside & landing
  - **Defect**: Stepped fin under sloped ramp, hollow tray cavity continuation, step down and notch at landing connection. [Category 4, 6, 1]
  - **Certainty**: sure

### 72. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_side.png`
- **Location**: Ramp and side wall
  - **Defect**: Full unmerged triangulation mesh drawn over the sloped ramp side wall and walking surface; downward-hanging tooth/fin. [Category 3, 4, 7]
  - **Certainty**: sure

### 73. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_top.png`
- **Location**: Ramp and lower landing
  - **Defect**: Dense fan of unmerged triangulation diagonals across the entire sloped ramp surface; ramp junction notches and teeth; chamfered corner spur line. [Category 3, 4]
  - **Certainty**: sure

### 74. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/nx.png`
- **Location**: Upper landing & ramp
  - **Defect**: Hollow recessed cavity under upper landing, downward tooth, ramp profile with unmerged triangulation lines on the ramp side wall. [Category 6, 4, 3]
  - **Certainty**: sure

### 75. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/ny.png`
- **Location**: Middle slabs & ramp
  - **Defect**: Hanging panels at different depths, see-through gaps between panels, stepped fins, unmerged triangulation lines on ramp. [Category 1, 4, 7, 3]
  - **Certainty**: sure

### 76. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_bot_a.png`
- **Location**: Underside
  - **Defect**: Hollow tray cavity in middle slabs, stepped fin under ramp, see-through slot under upper landing, corner notch. [Category 6, 1, 4, 2]
  - **Certainty**: sure

### 77. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_bot_b.png`
- **Location**: Underside
  - **Defect**: Hollow tray cavity, stepped fin under ramp, hanging panels at different depths with open slots. [Category 6, 1, 4, 2]
  - **Certainty**: sure

### 78. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_top_a.png`
- **Location**: Entire model
  - **Defect**: Stepped hanging skirt panels, ramp junction notches, transverse seams, plus full unmerged triangulation fan drawn across sloped ramp and landing. [Category 3, 4, 7]
  - **Certainty**: sure

### 79. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_top_b.png`
- **Location**: Entire model
  - **Defect**: Hanging skirt panels, ramp notches, plus unmerged triangulation fan drawn across ramp and landing. [Category 3, 4, 7]
  - **Certainty**: sure

### 80. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/px.png`
- **Location**: Profile
  - **Defect**: Vertical seams, knife-edge thin slab on left arm, ramp profile. [Category 3, 4, 7]
  - **Certainty**: sure

### 81. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/py.png`
- **Location**: Profile
  - **Defect**: Abrupt slab thickness change, stepped hanging piece, lines drawn on vertical wall, unmerged triangulation lines. [Category 4, 3, 7]
  - **Certainty**: sure

### 82. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/side_low_a.png`
- **Location**: Grazing side view
  - **Defect**: See-through holes under middle slabs, hanging skirt panels at uneven depths, open cavity, plus triangulation lines on ramp. [Category 1, 4, 6, 3]
  - **Certainty**: sure

### 83. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/side_low_b.png`
- **Location**: Low side view
  - **Defect**: Stepped elevation changes, varying slab thicknesses. [Category 4, 7]
  - **Certainty**: sure

### 84. `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/top.png`
- **Location**: Lower landing and sloped ramp (region 309)
  - **Defect**: Full unmerged triangulation fan drawn across the entire surface of the ramp and landing. [Category 3]
  - **Certainty**: sure
- **Location**: Horizontal arm and ramp junction
  - **Defect**: Transverse seam lines, notches/teeth at inner corner, chamfered corner spur line. [Category 3, 4]
  - **Certainty**: sure

---

## Part 5: Merged & Ranked Distinct Problems (Per-File)

### FILE A (`CHTM_SIDE_WALK_2nd_floor`)

#### Ranked Distinct Problems (Ranked by Visibility and Impact):

1. **Problem A1: Dense line clutter inside flat surface on the big landing (x ≈ 2673.2)**
   - **Visibility Rank**: 1 (Most prominent top-view visual flaw)
   - **Category**: (3) Line drawn inside a flat surface that is not an edge of the model
   - **Images showing it**:
     - `A-skp-render/top.png`, `A-skp-render/bottom.png`, `A-skp-render/chunk2_top.png`, `A-skp-render/chunk2_bottom.png`, `A-skp-render/obl_top_a.png`, `A-skp-render/obl_top_b.png`, `A-skp-render/obl_bot_a.png`, `A-skp-render/obl_bot_b.png`, `A-skp-render/px.png`, `A-skp-render/nx.png`, `A-skp-render/py.png`, `A-skp-render/ny.png`, `A-skp-render/side_low_a.png`
     - `CHTM_SIDE_WALK_2nd_floor-qa/top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_bottom.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_b.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_b.png`, `CHTM_SIDE_WALK_2nd_floor-qa/nx.png`, `CHTM_SIDE_WALK_2nd_floor-qa/ny.png`, `CHTM_SIDE_WALK_2nd_floor-qa/side_low_a.png`
   - **Description**: Along the outer right margin of the large polygon landing, a long longitudinal line runs along x ≈ 2673.2 parallel to the outer border, accompanied by a dense ladder of rectangular cells, triangles, and stray line segments cutting into both the top and bottom surfaces. `skp_edge_audit` confirms 17 visible lines inside flat same-material surfaces (20.3 ft total), with three of the longest lying along x = 2673.2.
   - **Cause & Engine Stage**: Planar merge skipped or split narrow strip regions along this boundary, or failed to dissolve collinear sub-edges where multiple coplanar faces meet. Needs planar merge border dissolution / `skp_writer` softening.

2. **Problem A2: Stepped terrace lines and radial cuts across the lower landing underside**
   - **Visibility Rank**: 2
   - **Category**: (3) Line drawn inside flat surface, (4) Stepped slab underside, (6) Incomplete bottom floor
   - **Images showing it**:
     - `A-skp-render/bottom.png`, `A-skp-render/chunk0_bottom.png`, `A-skp-render/obl_bot_a.png`, `A-skp-render/obl_bot_b.png`
     - `CHTM_SIDE_WALK_2nd_floor-qa/bottom.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_bottom.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_b.png`
   - **Description**: The bottom surface of the lower landing (chunk 0) is not a single unified planar floor. Instead, a series of stepped contour lines runs across the underside, partitioning it into stepped elevation terraces. Long radial lines also cut inward across the big landing bottom.
   - **Cause & Engine Stage**: Solidify bottom-capping unresolved across adjacent sub-regions (brief 10 item 3 / regions 467, 166, 244 where bottom faces were refused or capped at shallow depths due to hanging side walls).

3. **Problem A3: Continuous see-through slot / gap separating the curb block from the lower landing**
   - **Visibility Rank**: 3
   - **Category**: (1) Hole or see-through gap in a surface, (5) Loose / separated piece
   - **Images showing it**:
     - `A-skp-render/top.png`, `A-skp-render/bottom.png`, `A-skp-render/chunk0_top.png`, `A-skp-render/chunk0_bottom.png`, `A-skp-render/chunk0_side.png`, `A-skp-render/obl_top_a.png`, `A-skp-render/obl_top_b.png`, `A-skp-render/obl_bot_a.png`, `A-skp-render/obl_bot_b.png`, `A-skp-render/py.png`, `A-skp-render/ny.png`, `A-skp-render/side_low_a.png`, `A-skp-render/side_low_b.png`
     - `CHTM_SIDE_WALK_2nd_floor-qa/top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/bottom.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_bottom.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_side.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_b.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_b.png`, `CHTM_SIDE_WALK_2nd_floor-qa/py.png`, `CHTM_SIDE_WALK_2nd_floor-qa/ny.png`, `CHTM_SIDE_WALK_2nd_floor-qa/side_low_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/side_low_b.png`
   - **Description**: A long rectangular curb block along the far-left edge is separated from the main landing slab by a continuous vertical slot. You can see background light straight through from top to bottom.
   - **Cause & Engine Stage**: Input geometry architecture: the curb block is an independent solid body separated by an intentional expansion joint or gap, but its interior facing walls must be properly closed so neither side looks hollow or unsolidified.

4. **Problem A4: Jagged, sawtooth perimeter edge and triangular shard lines on big landing**
   - **Visibility Rank**: 4
   - **Category**: (4) Jagged, sawtooth or stepped slab side, (3) Line drawn inside flat surface
   - **Images showing it**:
     - `A-skp-render/bottom.png`, `A-skp-render/chunk2_bottom.png`, `A-skp-render/chunk2_side.png`, `A-skp-render/obl_bot_a.png`, `A-skp-render/obl_bot_b.png`, `A-skp-render/side_low_a.png`, `A-skp-render/nx.png`
     - `CHTM_SIDE_WALK_2nd_floor-qa/bottom.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_bottom.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_side.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_bot_b.png`, `CHTM_SIDE_WALK_2nd_floor-qa/side_low_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/nx.png`
   - **Description**: The angled bottom-right perimeter of the big landing has jagged, notched sawtooth irregularities on the top rim, and a series of triangular shard lines and stepped teeth along the underside boundary.
   - **Cause & Engine Stage**: Merge border simplification / collinear vertex pruning (0.15 in tolerance) created micro-teeth, or side rebuild generated stepped wall segments along an irregular outline.

5. **Problem A5: Multi-tiered / overlapping slab layers hanging under lower landing**
   - **Visibility Rank**: 5
   - **Category**: (4) Stepped slab side / underside, (7) Inconsistent slab thickness
   - **Images showing it**:
     - `A-skp-render/px.png`, `A-skp-render/chunk0_side.png`, `A-skp-render/chunk1_side.png`, `A-skp-render/py.png`, `A-skp-render/ny.png`
     - `CHTM_SIDE_WALK_2nd_floor-qa/px.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_side.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk1_side.png`, `CHTM_SIDE_WALK_2nd_floor-qa/py.png`, `CHTM_SIDE_WALK_2nd_floor-qa/ny.png`
   - **Description**: Looking horizontally at the lower landing profile, the slab underside is composed of multiple overlapping horizontal planes hanging at different heights, producing a staggered, stepped edge instead of a single clean vertical wall and flat bottom.
   - **Cause & Engine Stage**: Solidify underside classification and local wall depths resolved independently per region rather than unifying the slab envelope.

6. **Problem A6: Transverse seam lines across the walkway bridge and step lines on sloped landing**
   - **Visibility Rank**: 6
   - **Category**: (3) Line drawn inside a flat surface, (4) Stepped seam
   - **Images showing it**:
     - `A-skp-render/top.png`, `A-skp-render/chunk0_top.png`, `A-skp-render/chunk1_top.png`, `A-skp-render/chunk1_side.png`, `A-skp-render/chunk1_bottom.png`, `A-skp-render/obl_top_a.png`, `A-skp-render/obl_top_b.png`
     - `CHTM_SIDE_WALK_2nd_floor-qa/top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk1_top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk1_side.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk1_bottom.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_b.png`
   - **Description**: Transverse lines cut directly across the walkway bridge surface midway and at the junction with the big slab. A diagonal step line pattern also cuts across the sloped lower landing.
   - **Cause & Engine Stage**: Planar merge boundary between adjacent rectangular regions of the walkway; needs coplanar merge or edge softening in `skp_writer`.

7. **Problem A7: Unmerged triangulation fan drawn in QA sheet across lower landing**
   - **Visibility Rank**: 7 (Specific to engine QA render)
   - **Category**: (3) Line drawn inside a flat surface
   - **Images showing it**:
     - `CHTM_SIDE_WALK_2nd_floor-qa/top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk0_top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/obl_top_b.png`, `CHTM_SIDE_WALK_2nd_floor-qa/side_low_a.png`, `CHTM_SIDE_WALK_2nd_floor-qa/nx.png`, `CHTM_SIDE_WALK_2nd_floor-qa/px.png`
   - **Description**: The lower landing top surface is rendered in QA sheets with a large radial fan of triangle edges radiating from the lower-left corner to the curved inner edge. SketchUp hides these edges, but the QA sheet draws them because the region was copied through unmerged (146 copied triangles).
   - **Cause & Engine Stage**: Planar merge skipped the region (due to non-convex ring / T-junction / complex hole) and copied through its triangles.

8. **Problem A8: Isolated floating specks / dots on the big landing**
   - **Visibility Rank**: 8
   - **Category**: (5) Floating or loose piece
   - **Images showing it**:
     - `A-skp-render/top.png`, `A-skp-render/bottom.png`, `A-skp-render/chunk2_top.png`, `A-skp-render/chunk2_bottom.png`
     - `CHTM_SIDE_WALK_2nd_floor-qa/top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_top.png`, `CHTM_SIDE_WALK_2nd_floor-qa/chunk2_bottom.png`
   - **Description**: Isolated dots or tiny speck lines appear in the middle of the flat top and bottom surfaces of the big landing.
   - **Cause & Engine Stage**: Stray zero-length edge or tiny debris fragment surviving fragment detection.

---

### FILE B (`CHTM_2nd_to_3rd_building_sidewalk_outside`)

#### Ranked Distinct Problems (Ranked by Visibility and Impact):

1. **Problem B1: Middle slabs look hollow like an upside-down tray from below (missing bottom floor)**
   - **Visibility Rank**: 1 (Most critical architectural defect)
   - **Category**: (6) Slab that looks hollow like a tray from below, (1) Hole / missing surface, (2) Face showing its back side
   - **Images showing it**:
     - `B-skp-render/bottom.png`, `B-skp-render/chunk1_bottom.png`, `B-skp-render/obl_bot_a.png`, `B-skp-render/obl_bot_b.png`, `B-skp-render/chunk0_bottom.png`, `B-skp-render/chunk2_bottom.png`, `B-skp-render/side_low_a.png`, `B-skp-render/nx.png`
     - `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/bottom.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_bottom.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_bot_a.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_bot_b.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk0_bottom.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_bottom.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/side_low_a.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/nx.png`
   - **Description**: The middle slabs along the horizontal walkway arm have vertical side walls, but NO solid bottom floor! The underside is an open, hollow recessed cavity with exposed interior perimeter walls and partition lines. Anyone looking from below sees straight into the empty tray, exposing the back faces of the walking surface (which display blue-purple in SketchUp GUI).
   - **Cause & Engine Stage**: Brief 10 item 1: Cap guard refuses needed walls and bottoms separately because each is tested against a mesh missing the other, causing the bottom to be rejected. Also `max_thickness` (36 in) is below the file's 39.37 in blocks (region 92), stopping bottom generation.

2. **Problem B2: Stepped fin / hanging wall underneath the sloped ramp**
   - **Visibility Rank**: 2
   - **Category**: (4) Stepped slab side, (7) Unwanted hanging projection
   - **Images showing it**:
     - `B-skp-render/bottom.png`, `B-skp-render/chunk2_bottom.png`, `B-skp-render/chunk1_side.png`, `B-skp-render/chunk2_side.png`, `B-skp-render/obl_bot_a.png`, `B-skp-render/obl_bot_b.png`, `B-skp-render/ny.png`
     - `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/bottom.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_bottom.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_bot_a.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_bot_b.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/ny.png`
   - **Description**: Underneath the sloped ramp (region 309 / chunk 2), a vertical stepped fin / wall hangs downward into open air below the slab bottom. It extends downward past the slab's natural thickness.
   - **Cause & Engine Stage**: Side rebuild SR2/SR5 wall generation projected an outline wall down to a lower floor or reference plane that did not belong to the ramp's own thickness (brief 10 item 6 / R2-I2).

3. **Problem B3: Hanging skirt panels at different depths with see-through open slots under walkway**
   - **Visibility Rank**: 3
   - **Category**: (1) Hole / see-through gap in surface, (4) Jagged / stepped slab side, (7) Panels hanging at inconsistent depths
   - **Images showing it**:
     - `B-skp-render/chunk1_side.png`, `B-skp-render/ny.png`, `B-skp-render/side_low_a.png`, `B-skp-render/chunk0_side.png`, `B-skp-render/obl_bot_a.png`, `B-skp-render/obl_bot_b.png`, `B-skp-render/py.png`
     - `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/ny.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/side_low_a.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk0_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_bot_a.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_bot_b.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/py.png`
   - **Description**: Under the middle walkway (chunk 1), vertical skirt panels hang down at 3 to 4 distinctly different depths like crenellations or hanging teeth. Between these panels, there are see-through open slots where light passes completely through under the slab.
   - **Cause & Engine Stage**: Brief 10 item 6: Wall generation calculated different depths for adjacent edge segments, and the cap guard removed intermediate wall segments that failed exposure, leaving open vertical slots.

4. **Problem B4: Sawtooth / jagged cutout notches and teeth at the ramp junction (SR6 ramp teeth)**
   - **Visibility Rank**: 4
   - **Category**: (4) Jagged, sawtooth or stepped slab side, (1) Notch / cutout in surface
   - **Images showing it**:
     - `B-skp-render/top.png`, `B-skp-render/chunk1_top.png`, `B-skp-render/chunk2_top.png`, `B-skp-render/chunk1_side.png`, `B-skp-render/chunk2_side.png`, `B-skp-render/obl_top_a.png`, `B-skp-render/obl_top_b.png`, `B-skp-render/bottom.png`, `B-skp-render/chunk1_bottom.png`, `B-skp-render/chunk2_bottom.png`
     - `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/top.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_top.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_top.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_top_a.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_top_b.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/bottom.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_bottom.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_bottom.png`
   - **Description**: At the inner corner where the sloped ramp meets the walkway, there is an irregular triangular notch cutout in the walking surface, accompanied by a sharp downward-pointing tooth / fin. Small rectangular notches also indent the walkway perimeter.
   - **Cause & Engine Stage**: Known issue from brief 10 item 5 (`B_sr6_ramp_teeth_v0.png`): residual back-facing piece left at the upper-left end of the ramp close-up, where side rebuild replaced partial pieces but left a small tooth.

5. **Problem B5: Internal criss-cross wireframe struts visible inside open underside cavity**
   - **Visibility Rank**: 5
   - **Category**: (7) Internal geometry visible through missing bottom, (3) Line drawn inside hollow volume
   - **Images showing it**:
     - `B-skp-render/chunk0_side.png`, `B-skp-render/chunk1_side.png`, `B-skp-render/side_low_a.png`
     - `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk0_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk1_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/side_low_a.png`
   - **Description**: Looking horizontally under the cantilever slab and walkway into the hollow underside cavity, interior diagonal criss-cross lines / truss struts are clearly visible inside the empty volume.
   - **Cause & Engine Stage**: Internal structural lines or edges exposed because the bottom cap was never placed to occlude the interior.

6. **Problem B6: Transverse seam lines, T-junction lines, and chamfered corner spur**
   - **Visibility Rank**: 6
   - **Category**: (3) Line drawn inside flat surface that is not an edge of the model
   - **Images showing it**:
     - `B-skp-render/top.png`, `B-skp-render/chunk0_top.png`, `B-skp-render/chunk2_top.png`, `B-skp-render/px.png`, `B-skp-render/obl_top_a.png`, `B-skp-render/obl_top_b.png`, `B-skp-render/bottom.png`
     - `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/top.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk0_top.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_top.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/px.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_top_a.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_top_b.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/bottom.png`
   - **Description**: Transverse seam lines divide the walkway into distinct segments. At the chamfered corner of the lower landing, an internal spur line cuts into the flat surface from the perimeter edge. `skp_edge_audit` reports 20 visible T-junction lines lying on a flat surface (42.3 ft total).
   - **Cause & Engine Stage**: Material boundary seams (19 visible coplanar material borders) and T-junction edges lying on coplanar faces.

7. **Problem B7: Unmerged triangulation fan drawn in QA sheet across sloped ramp and landing**
   - **Visibility Rank**: 7 (Specific to engine QA render)
   - **Category**: (3) Line drawn inside a flat surface
   - **Images showing it**:
     - `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/top.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_top.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/chunk2_side.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_top_a.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/obl_top_b.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/nx.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/ny.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/side_low_a.png`
   - **Description**: The sloped ramp (region 309) and adjacent landing are drawn in the engine QA sheet with all internal triangulation diagonals fanning across the walking surface and side walls (42 copied triangles). SketchUp hides these edges, but the QA sheet exposes them because region 309 was copied through unmerged.
   - **Cause & Engine Stage**: Planar merge skipped region 309 due to boundary complexity or non-coplanar vertex alignment.

8. **Problem B8: Paper-thin / knife-edge cantilever walkway profile**
   - **Visibility Rank**: 8
   - **Category**: (7) Inconsistent slab thickness, (4) Stepped slab side
   - **Images showing it**:
     - `B-skp-render/px.png`, `CHTM_2nd_to_3rd_building_sidewalk_outside-qa/px.png`
   - **Description**: Seen directly from the +X side view (`px.png`), the far-left walkway slab tapers down to zero thickness, appearing like a single flat sheet / knife edge without vertical depth.
   - **Cause & Engine Stage**: Missing side walls or bottom along the cantilever terminus.
