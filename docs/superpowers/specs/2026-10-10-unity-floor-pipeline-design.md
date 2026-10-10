# Unity floor pipeline: engine-fixed floors that stay fixed in Unity (design)

**Status:** owner-approved direction, 2026-10-10. This spec is for the owner's review before any plan or code.
**Scope:** building floors and elements only (the units of `data/campus/campus_map.json`). The environment (terrain,
roads, water, rocks: `Assets/Models/Env/`) stays outside the engine, as the owner already keeps it separate.

## 1. The problem (owner, 2026-10-10)

- The owner sometimes fixes the model with AI inside Unity, and sometimes in Blender. Those fixed versions have no
  "original file" the engine knows about, so a rebuild can undo or duplicate them.
- **The engine's own fixed OBJ breaks when Unity imports it**, on the route "Engine OBJ → Unity". The symptoms:
  - holes or missing faces;
  - spikes or stretched triangles;
  - black, dark or inside-out faces;
  - wrong or missing textures.
- **The owner cannot spot every error by eye in Unity** (flicker, for example). So the pipeline cannot rely on the
  owner finding errors. **The engine must find them itself, in its own build and in what Unity actually shows.**
- The owner wants a record of each floor or building **outside Unity**.

## 2. Measured facts (read-only, 2026-10-10)

- **The Unity project** is `D:/PROJECTS/UC/01-UNITY/UC-Campus`, on Unity 6000.4.7f1 with URP 17.4.0.
  - It holds 693 campus OBJ files under `Assets/Models/Campus/` (CKPT5-CKPT17, CHTM-Fresh) and 74 environment
    files under `Assets/Models/Env/`.
  - Unity reads the OBJ files with its own importer.
- **`Assets/Editor/CampusModelImporter.cs` (an `AssetPostprocessor`)** sets, for every building model under
  `Assets/Models/Campus/`:
  - `weldVertices = true`;
  - `importNormals = Calculate`, with tangents `CalculateMikk`;
  - `generateSecondaryUV`, which unwraps lightmap UVs;
  - `addCollider = true`, `isReadable = true`, compression off;
  - a global scale (inches to metres) unless the path is pre-scaled.

  Each of these changes the geometry or its shading after the engine has written it. They are **suspects, not
  proven causes**; section 4 measures them.
- **Other editor scripts already measure the model:** `CampusAudit.cs`, `CampusDefectAudit.cs` and
  `CampusBuildingFloors.cs`. `CampusDoubleSided.cs` draws both sides (`_Cull = 0`).
- **The engine's error finder** (`engine/detectors/errors.py::find_errors`) knows 7 kinds: flicker (by material and
  by look), reversed, hidden, loose, open edges and cracks. The Validator judges to the owner's floor (AGENTS.md
  §5, "Visible rule, measured").

## 3. The design: four parts, built in this order

### Part 1: the Unity import check (built first; it answers "is the engine's fix still there in Unity?")

1. **A Unity editor script `UcFloorExport.cs`.**
   - It lives in this repo under `unity/Editor/` and is copied into the Unity project only with the owner's OK.
   - For one floor's GameObject (or its imported model asset), it writes **exactly what Unity made of it**:
     - vertices, triangles, normals and UVs per submesh;
     - the material and texture per submesh;
     - the importer settings in force.
   - Output is an OBJ+MTL plus a JSON sidecar, in world coordinates, written to a folder outside the Unity project.
   - It never saves a scene or changes an asset.
2. **The engine's `engine.cli unity-check --build <engine floor OBJ> --unity <exported OBJ>`.** It compares the two
   with the engine's own tools:
   - face, vertex and triangle counts;
   - `find_errors` per kind, on both;
   - the Validator's before/after pictures, with the engine build as BEFORE and Unity's copy as AFTER, so any face
     Unity lost, moved or re-textured fails;
   - a per-cause breakdown: welded vertices, recomputed normals, UVs changed, materials remapped, faces dropped,
     submesh splits.
3. **Pass rule:** a floor is "Unity-safe" only when Unity's copy has the same faces, looks and UVs as the engine
   build, and `find_errors` on Unity's copy is no worse than on the build.

### Part 2: a Unity-safe export, then the per-floor loop

1. Part 1 measures each suspect import setting in section 2, one at a time, on golden floors (CHTM 5th, sidewalks A
   and B). From that, the engine writes the format and settings that pass, for example:
   - explicit per-face normals;
   - no weld;
   - 32-bit index buffers;
   - lightmap UVs written by the engine, or turned off.
   - Any change to `CampusModelImporter.cs` for building floors needs the owner's OK. It is proposed as a diff with
     measurements, never applied silently.
2. **The per-floor loop**, automatic and per unit:
   1. **Scan what Unity has now.** `UcFloorExport` exports the floor as Unity shows it, and the engine runs
      `find_errors`. The result is the floor's error map in the dashboard, with pictures; no eyes are needed.
   2. **Repair.** `engine.cli repair-unit`, with every engine merged so far.
   3. **Validate** to the owner's floor.
   4. **Import check (Part 1).** The floor goes to Unity only if Unity's copy passes.
   5. **Swap.** A Unity editor action replaces only that floor's object. The owner triggers it at first.
3. **Triggers:**
   - the owner selects a floor in Unity and runs "Check & fix this floor";
   - or a batch over all floors, as a queued job (`tools/jobs.py`).

### Part 3: learning from the owner's Unity fixes and marks

- **A Unity mark ("this is wrong here"):**
  - the editor script records the floor, the world position, an optional note and a screenshot as a request;
  - the request becomes a queued job for that unit;
  - it also becomes a test fixture (the existing rule: every spot the owner marks wrong becomes a fixture).
- **A hand fix in Unity (or Blender):**
  - `UcFloorExport` exports the fixed floor;
  - the engine compares it with its latest build and records the difference as an example, with the Validator's
    verdict;
  - accepted examples become fixtures, then rules;
  - the ML stage (P4) learns from them and never bypasses the rules (AGENTS.md §5, ML).

### Part 4: the floor record outside Unity

- **One folder per unit:** `MODEL FIXER ENGINE FILES\05-FIXING\<BUILDING>\<Lnn>\` (or the element name), holding:
  - `versions/`: v000 = CHECKPOINT-17, then each engine build or imported Unity/Blender fix, each with its OBJ,
    `report.json`, `validation.json`, the Unity check result and pictures;
  - `in_unity.json`: which version is in Unity now, and when it was swapped;
  - `requests/`: the owner's marks and their jobs;
  - `needs_modelling.json`: spots the engine cannot fix.
- **The dashboard** reads the same records. Only results built from committed code are published there
  (AGENTS.md §3).
- **The tracked current version** is per unit. The engine always repairs from the latest accepted version, so an
  accepted Unity or Blender fix is never undone.

## 4. Error handling and proof

- **The exporter's own check.** `UcFloorExport` runs its round-trip on an untouched engine build first. If Unity's
  copy differs, the report says why, by cause. That is the import diagnosis itself.
- **No swap without a pass.** A floor whose Unity copy fails the check is never swapped in. The report names the
  cause.
- **Every tool's output is snapshotted with sha256**, as `engine/io/snapshot.py` does today, so a record can never
  point at a file that changed later.

## 5. Testing

- **Engine side (pytest):**
  - `unity-check` on synthetic pairs: an identical pair passes. Each of these must fail with its cause named:
    - a welded pair of coincident vertices;
    - recomputed normals that flip a face;
    - a dropped submesh;
    - a remapped material;
    - a shifted UV.
- **Unity side:**
  - `UcFloorExport` on a tiny known OBJ inside the Unity project: the exported OBJ matches the input under a no-op
    importer preset.
  - It runs through the Unity CLI or Unity MCP in batch mode. This needs the owner's OK to run Unity headless or in
    the open editor.
- **Golden floors:** CHTM 5th and sidewalks A and B, with the engine build → Unity → `unity-check` table before and
  after the import-setting changes.

## 6. Out of scope

- The environment models.
- Fixing inside Unity with C# (the engine stays the one repair tool).
- Blender as a repair route. Blender is only a source of owner fixes, imported like a Unity fix.

## 7. Open points for the owner

1. Copying `UcFloorExport.cs` (and later the swap action) into the Unity project's `Assets/Editor/`, and running it
   from the Unity CLI or MCP. This needs your OK when Part 1 starts.
2. Any change to `CampusModelImporter.cs` for building floors will be proposed with measurements and needs your OK.
3. Part 2's swap is manual (you press the button) until you say it may run automatically.
