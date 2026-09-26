# Task 8 Report: Error Filter Logic

## Status
✅ COMPLETE

## Summary
Pure TypeScript logic for the 3D error filter implemented and fully tested. All 8 unit tests pass, all 55 vitest tests pass across 9 test files, and TypeScript compilation validates with only the 3 pre-existing errors in Viewport.ts (Task 9 fixes those).

## Commit
SHA: `c434aaf`

## Test Results

### errorLayers.test.ts (8 passed)
```
 Test Files  1 passed (1)
      Tests  8 passed (8)
```

### All vitest (55 passed across 9 test files)
```
 Test Files  9 passed (9)
      Tests  55 passed (55)
```

### TypeScript Compilation
Pre-existing errors only (as expected):
- `src/three/Viewport.ts(332,34)`: Property 'side' does not exist on type 'Material | Material[]'
- `src/three/Viewport.ts(333,34)`: Property 'needsUpdate' does not exist on type 'Material | Material[]'
- `src/three/Viewport.ts(360,21)`: Argument of type 'number | null' is not assignable to parameter of type 'number'

No new TypeScript errors introduced.

## Delivered
- `web/src/utils/errorLayers.ts` — All 15 functions and 3 interfaces per brief
- `web/src/utils/errorLayers.test.ts` — All 8 tests from brief, all passing

## Concerns
None. Implementation matches brief exactly, all tests pass, no breaking changes.

---

## Fix Round 1: Performance Optimization

**Issue:** `blinkColors` called `partnersOf` for every face, scanning all `flicker_pairs` each time — O(faces × pairs). On real buildings (~10,000 flicker faces × 13,947 pairs), this was ~139 million steps per blink toggle, freezing the viewer.

**Solution:** 
- Added `partnerIndex(file): Map<number, { face: number; shared: number; opposite: boolean }[]>` that builds the lookup map once in O(pairs) and caches it per file object via a module-level `WeakMap<ErrorsFile, ...>`
- Updated `partnersOf(file, face)` to return `partnerIndex(file).get(face) ?? []` — same results and order, existing test stays green
- Updated `blinkColors` to use `partnerIndex(file)` directly — one lookup per face, no function call overhead

**Commit:** SHA `6a5b17b`

**Test Results:**
- errorLayers.test.ts: 9 passed (8 original + 1 new performance test)
- All vitest: 56 passed (55 original + 1 new)
- Performance test: 40,000 faces with 20,000 pairs completes in <1,000 ms (was seconds with quadratic code)
- TypeScript: 3 pre-existing Viewport.ts errors, no new errors

**Delivered:**
- `partnerIndex()` function with WeakMap caching
- Updated `partnersOf()` and `blinkColors()` to use cached lookup
- Performance test: `blinkColors(bigFile, 40k faces, mat, 1)` asserts <1,000 ms and correct phase-swap colours

**Concerns:**
None. Optimization eliminates O(faces × pairs) bottleneck, all tests pass.
