# Task 12 Report: Meshbuf Caching

## Status: COMPLETED

## Commit
- SHA: `91cde5a6d112a4450a21d5417833fb3b22c94ce7`
- Branch: `feat/error-filter`

## Files Modified
1. `api/routers/versions.py`
   - Added `import struct` at top
   - Added helper `meshbuf_cache_file(settings, version_id)` to generate cache file path
   - Added helper `_meshbuf_response(buf)` to create Response from cached bytes
   - Modified `get_meshbuf()` to check cache first, then write atomically on first access

2. `api/tests/test_versions.py`
   - Added test `test_meshbuf_is_built_once_per_version` that:
     - Gets meshbuf for a version
     - Monkeypatches `pack_meshbuf` to raise AssertionError
     - Verifies second request doesn't call pack_meshbuf again
     - Checks response content and headers are identical

## Test Results
All 7 tests in `api/tests/test_versions.py` pass:
```
.......
7 passed, 4 warnings in 162.16s
```

- `test_get_meshbuf` - existing test still passes
- `test_run_fix_endpoint` - existing test still passes
- `test_fixed_version_keeps_materials_and_textures` - existing test still passes
- `test_m5_backfill_null_asset_sha256` - existing test still passes
- `test_face_picking_endpoint_for_snapshot_and_fixed` - existing test still passes
- `test_get_version_run` - existing test still passes
- `test_meshbuf_is_built_once_per_version` - NEW, verifies caching works

## Implementation Details

### Cache Location
Meshbuf files are stored at: `settings.data_dir / "meshbuf" / f"version-{version_id}.bin"`

### Atomic Write
- Write to temporary file: `version-{id}.bin.tmp`
- Use `Path.replace()` to atomically move to final location
- Directory created with `parents=True, exist_ok=True`

### Cache Retrieval
- Check `cached.exists()` right after version validation
- Return cached response immediately if found
- Response includes same headers and body as first request

### Binary Format Handling
- Cache file is the complete binary meshbuf (starts with "UCMB" magic)
- `_meshbuf_response()` extracts face count from header:
  - Reads header length from bytes 8-12 as little-endian uint32
  - Parses JSON metadata from bytes 12-12+hlen
  - Extracts face count from metadata
  - Returns Response with X-Tris-Count and X-Face-Count headers

## Concerns
None. All requirements met:
- Caching works correctly (second request skips pack_meshbuf)
- Response headers are identical
- All existing tests pass
- Atomic write prevents corruption on concurrent access
- Cache survives across requests

## Fix Round 1

### Issues Found and Fixed

**Commit: `20270b0a235297187701d4821b9a714e02898f72`**

1. **Critical: Shared temp name** - Fixed concurrent write corruption
   - Changed from fixed `version-{id}.bin.tmp` to unique `tempfile.mkstemp()`
   - Write through file descriptor: `os.fdopen(fd, "wb")`
   - Atomic rename with `os.replace(tmp_path, cached)`
   - Proper cleanup: `os.unlink(tmp)` in exception handler

2. **Important: Cache format guard** - Validate format before serving
   - Added `_is_valid_meshbuf_format()` helper to check MAGIC and VERSION
   - Imports MAGIC and VERSION from `engine.transport.meshbuf`
   - Cache is rebuilt if format doesn't match (e.g., after a format upgrade)
   - Test: `test_meshbuf_cache_format_guard` plants wrong-version cache and verifies rebuild

3. **Important: Immutability comment** - Documented cache assumptions
   - Added comment explaining versions are immutable
   - Notes about importer's `flat_materials` backfill convergence
   - Migration guidance: "if that backfill ever changes, delete data/meshbuf/"

4. **Minor: content-type assertion** - Extended existing test
   - Added assertion: `second.headers["content-type"] == first.headers["content-type"]`
   - Ensures headers are identical across cached responses

### Test Results After Fixes
```
........
8 passed, 4 warnings in 221.67s
```

- 7 original tests still pass
- `test_meshbuf_is_built_once_per_version` - caching works
- `test_meshbuf_cache_format_guard` - NEW, format validation works
