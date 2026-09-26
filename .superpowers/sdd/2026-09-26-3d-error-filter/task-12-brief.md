### Task 12: the meshbuf is built once per version (added 2026-09-26 after the owner saw an empty panel)

The owner opened CHTM 5th floor, and both panels stayed blank for about 19 s. `GET /api/versions/6/meshbuf`
takes 12.5 s (measured): `analyse_topology` over 20,599 faces and 26,856 edges on every request.
Versions never change, so the packed meshbuf is kept on disk the first time.

**Files:**
- Modify: `api/routers/versions.py` (`get_meshbuf`)
- Test: `api/tests/test_versions.py` (append)

- [ ] **Step 1: Write the failing test** (append to `api/tests/test_versions.py`)

```python
def test_meshbuf_is_built_once_per_version(client, imported_cube, monkeypatch):
    import api.routers.versions as versions_mod
    vid = imported_cube["versions"][0]["id"]
    first = client.get(f"/api/versions/{vid}/meshbuf")
    assert first.status_code == 200

    def packed_again(*a, **k):
        raise AssertionError("packed again")

    monkeypatch.setattr(versions_mod, "pack_meshbuf", packed_again)
    second = client.get(f"/api/versions/{vid}/meshbuf")
    assert second.status_code == 200
    assert second.content == first.content
    assert second.headers["x-tris-count"] == first.headers["x-tris-count"]
```

- [ ] **Step 2: Run it and see it fail** (the second call packs again and raises "packed again", which surfaces as a 500 or an AssertionError).

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_versions.py::test_meshbuf_is_built_once_per_version -q -p no:cacheprovider`

- [ ] **Step 3: Implement.** In `api/routers/versions.py`, add near the top:

```python
import struct


def meshbuf_cache_file(settings: Settings, version_id: int) -> Path:
    return settings.data_dir / "meshbuf" / f"version-{version_id}.bin"


def _meshbuf_response(buf: bytes) -> Response:
    hlen = struct.unpack("<I", buf[8:12])[0]
    faces = json.loads(buf[12:12 + hlen].decode("utf-8").strip())["counts"]["faces"]
    return Response(content=buf, media_type="application/octet-stream",
                    headers={"X-Tris-Count": str(faces), "X-Face-Count": str(faces),
                             "Cache-Control": "public, max-age=3600"})
```

In `get_meshbuf`, right after the `version is None` check, add:

```python
    cached = meshbuf_cache_file(settings, id)
    if cached.exists():
        return _meshbuf_response(cached.read_bytes())
```

Replace its final `return Response(...)` with:

```python
    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".bin.tmp")
    tmp.write_bytes(buf)
    tmp.replace(cached)
    return _meshbuf_response(buf)
```

(`json`, `Path` and `Response` are already imported in this file; check with
`grep -n "^import json\|^from pathlib\|Response" api/routers/versions.py` and add any that are missing.)

- [ ] **Step 4: Run the versions tests and see them pass**

Run: `.venv/Scripts/python.exe -m pytest api/tests/test_versions.py -q -p no:cacheprovider`

- [ ] **Step 5: Commit**

```bash
git add api/routers/versions.py api/tests/test_versions.py
git commit -m "perf(api): a version's meshbuf is built once and kept, not on every open" -m "CHTM 5th floor's meshbuf took 12.5 s per request (20,599 faces); versions never change." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

**Also, in Task 10 (added with this task):** show a loading message in each panel while its meshbuf
loads.
- In `WorkspaceView.vue` add `const loadingA = ref(false)` and `const loadingB = ref(false)`.
- Set each to `true` before its `fetchMeshbuf(...)` in `reloadModel()`, and back to `false` in a
  `finally`.
- In each panel's viewport container add:

  ```vue
  <div v-if="loadingA" class="panel-loading">Loading model… a large building can take 20 s the first time</div>
  ```

  and the same with `loadingB`.
- Style `.panel-loading` as a centred overlay: `position: absolute; inset: 0; display: flex;
  align-items: center; justify-content: center; background: rgba(246,246,248,0.85); color: #555;
  font-size: 14px; z-index: 2;`
- Make sure the viewport container is `position: relative`.

## Order

Tasks run in this order: **1, 2, 3, 4, 5, 6, 12, 8, 7, 9, 10, 11**.
- Task 8 comes before Task 7, because Task 7 imports Task 8's `ErrorsFile` type.
- Task 3 comes before Task 4 Step 5, which measures the whole building.

The profiling script used in Task 3 Step 5 is
`C:/Users/Future26/AppData/Local/Temp/claude/D--PROJECTS-UC-MODEL-FIXER/5472478e-978d-426b-bab2-e7cf21699a70/scratchpad/profile_double_layers.py`.
Copy it into `docs/superpowers/records/scripts/profile_double_layers.py` in Task 3 so the
measurement can be repeated.
