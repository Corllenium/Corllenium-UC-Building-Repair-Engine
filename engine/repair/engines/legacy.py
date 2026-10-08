"""The legacy engines (P1-K2): each stage of `engine.fixes.pipeline.fix_object`, wrapped as a
`RepairEngine` that runs the stage UNCHANGED and then records, as typed `Edit`s, what it changed.

Observe-only. The edits are not a plan the stage follows and nothing here changes a stage's
output: each wrapper runs its stage on the shared `FixState`, then compares the K1 `face_keys`
of the faces before the stage with the faces after it.

- Keys are a MULTISET: stacked exact duplicates are common in this data, so a key may occur more
  than once, and only the change in its count is an edit. When a key loses copies, the copies
  named removed are its LAST occurrences in the stage's input (any copy would do: they are the same
  snapped triangle with the same look).
- A key that loses a copy while its reversed-winding key gains one is a FLIP of that face.
- A key that loses a copy otherwise is a REMOVE; a key that gains one is an ADD.

| stage       | engine | what its edits are                                                     |
|-------------|--------|------------------------------------------------------------------------|
| solidify    | E8     | add (per material, carrying the points solidify invented); remove;     |
|             |        | flip, where a rebuilt side piece is an input face in reverse winding   |
| hidden      | E3, E1 | pass 1: remove. Labelled per face: E1 for a zero-area face (`~topo.ok`, |
|             |        | the mask pass 1 itself splits its counts by), E3 for a hidden one       |
| slit        | E3     | pass 2: remove (slit faces; only with `accept_slit`)                   |
| fragments   | E1     | remove (stray fragments, attached slivers, fold members)               |
| orientation | E2     | flip                                                                   |
| overlap     | E4     | remove (covered same-material duplicate layers)                        |
| merge       | E7     | cut, one per material: the region triangles it replaced, and the new   |
|             |        | triangulation from existing points only (never `new_points`)           |

Pass 1 has no mesh of its own -- `fix_object` drops pass 1's and pass 2's faces in one
`remove_faces` call -- so the face set pass 1 leaves is the reference's faces minus
`removed_pass1`, observed as a `FaceView` subset of the reference: a face's key depends only on
its own vertices and material, so the subset's keys are exactly the keys of those faces.

Every `Edit.faces` id indexes the stage's INPUT face set (the previous stage's output view), and
every `new_faces` vertex id the input mesh's positions, ids from `n` up naming the edit's own
`new_points` (K1's `apply_edits` convention). Every add and cut also carries, from the stage's
OUTPUT mesh, the UV and normal VALUES at each corner of its new faces (`new_face_uv`,
`new_face_normal`, K1b), so `apply_edits(stage_input, stage_edits)` reproduces the output's
per-corner values; a face whose output has no `vt` (or `vn`) stays without one. `Edit.evidence` holds the stage, the removed and added
keys and, for an add or cut, the material.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Callable

import numpy as np

from engine.fixes.pipeline import FIX_STAGES, FixProfile, FixState, start_fix
from engine.model import MeshData
from engine.repair.types import Edit, FaceKey, RepairContext, UnitState, face_keys

#: (stage, engine label) in `FIX_STAGES` order. "E3+E1": pass 1 logs E3 and E1 edits.
STAGE_ENGINES = (("solidify", "E8"), ("hidden", "E3+E1"), ("slit", "E3"), ("fragments", "E1"),
                 ("orientation", "E2"), ("overlap", "E4"), ("merge", "E7"))
assert [s for s, _ in STAGE_ENGINES] == [s for s, _ in FIX_STAGES], "STAGE_ENGINES out of step"

REASONS = {
    "solidify": "solidify: input faces replaced by a rebuilt side (remove) and faces closing the "
                "slab (add, with the points it invented)",
    "hidden": "pass 1: hidden faces (E3) and zero-area faces (E1) the strict guard confirmed",
    "slit": "pass 2: slit faces the colour-tolerant guard confirmed",
    "fragments": "stray fragments, attached slivers and fold members the rays and the fragment "
                 "guard confirmed",
    "orientation": "faces re-wound: only their back was exposed, or a thin sheet made consistent",
    "overlap": "covered same-material duplicate layers the strict guard confirmed",
    "merge": "region merge: a material's merged regions re-triangulated from existing points",
}


class FaceView:
    """The faces `ids` of `mesh` (all of them when `ids` is None), in that order: a stage's input or
    output face set. View face `k` is mesh face `ids[k]`."""

    def __init__(self, mesh: MeshData, ids: np.ndarray | None, looks: dict[int, str],
                 mesh_keys: list[FaceKey] | None = None):
        self.mesh = mesh
        self.ids = None if ids is None else np.asarray(ids, np.int64)
        self.looks = looks
        self._mesh_keys = mesh_keys
        self._keys: list[FaceKey] | None = None

    @property
    def n_faces(self) -> int:
        return self.mesh.n_faces if self.ids is None else len(self.ids)

    def mesh_keys(self) -> list[FaceKey]:
        """The keys of every face of `mesh` (not only the view's)."""
        if self._mesh_keys is None:
            self._mesh_keys = face_keys(self.mesh, self.looks)
        return self._mesh_keys

    @property
    def keys(self) -> list[FaceKey]:
        if self._keys is None:
            every = self.mesh_keys()
            self._keys = list(every) if self.ids is None else [every[i] for i in self.ids.tolist()]
        return self._keys

    def mesh_ids(self, view_ids) -> np.ndarray:
        view_ids = np.asarray(view_ids, np.int64)
        return view_ids if self.ids is None else self.ids[view_ids]

    def as_mesh(self) -> MeshData:
        """The view as a mesh of its own (same positions, UVs, normals and materials)."""
        if self.ids is None:
            return self.mesh
        m, k = self.mesh, self.ids
        return replace(m, face_v=m.face_v[k], face_vt=m.face_vt[k], face_vn=m.face_vn[k],
                       face_material=m.face_material[k], face_line=m.face_line[k])


def _reversed_keys(view: FaceView, view_ids: list[int]) -> list[FaceKey]:
    """The keys the faces `view_ids` of `view` would have with their winding reversed."""
    if not view_ids:
        return []
    k = view.mesh_ids(view_ids)
    m = view.mesh
    flipped = replace(m, face_v=m.face_v[k][:, ::-1], face_vt=m.face_vt[k], face_vn=m.face_vn[k],
                      face_material=m.face_material[k], face_line=m.face_line[k])
    return face_keys(flipped, view.looks)


def _last_copies(keys: list[FaceKey], surplus: Counter) -> list[int]:
    """Ids of the last `surplus[k]` occurrences of each key `k` in `keys`, ascending."""
    need = Counter(surplus)
    picked = []
    for i in range(len(keys) - 1, -1, -1):
        if need[keys[i]] > 0:
            need[keys[i]] -= 1
            picked.append(i)
    return picked[::-1]


def _new_faces(before: FaceView, after: FaceView, after_ids: list[int], stage: str):
    """`(new_faces, new_points)` of the after-view faces `after_ids`, in K1's convention: vertex ids
    of the BEFORE mesh, and ids from `n` up naming this edit's own new points (None when none).

    New points are numbered PER EDIT (K1: every edit counts its points from `n`). A point solidify
    invented that faces of two materials share -- so two E8 add edits -- is carried by each of
    them, and the sum of `n_new_points` over a run can exceed solidify's `invented_vertices`.
    K3 de-duplicates such points when it applies the edits."""
    n = len(before.mesh.positions)
    before_p, after_p = before.mesh.positions, after.mesh.positions
    if len(after_p) < n or not (after_p is before_p or np.array_equal(after_p[:n], before_p)):
        raise ValueError(f"{stage}: the stage moved or dropped a vertex, so its added faces cannot be "
                         f"written against its input's points")
    rows = after.mesh.face_v[after.mesh_ids(after_ids)].astype(np.int64)
    local = np.unique(rows[rows >= n])
    if not len(local):
        return rows, None
    renumbered = np.where(rows >= n, n + np.searchsorted(local, rows), rows)
    return renumbered, after_p[local]


def _corner_values(after: FaceView, after_ids: list[int]):
    """`(uv, normal)` of the after-view faces `after_ids`: (k, 3, 2) and (k, 3, 3) arrays of the
    values their corners hold in the stage's OUTPUT, for `Edit.new_face_uv` / `new_face_normal`.

    A face counts as having them only when all three corners index a row; any other face (an OBJ
    face without `vt` / `vn` has -1 at every corner) is written as the all-NaN placeholder `Edit`
    documents, so `apply_edits` gives it -1 again. When no face has any, that array is None."""
    mesh, ids = after.mesh, after.mesh_ids(after_ids)

    def gather(index: np.ndarray, table: np.ndarray, width: int) -> np.ndarray | None:
        has = (index >= 0).all(axis=1)
        if not has.any():
            return None
        out = np.full((len(index), 3, width), np.nan)
        out[has] = np.asarray(table, np.float64).reshape(-1, width)[index[has]]
        return out

    return (gather(mesh.face_vt[ids], mesh.uvs, 2), gather(mesh.face_vn[ids], mesh.normals, 3))


def observe(before: FaceView, after: FaceView, *, stage: str, site: int, engine: str,
            mode: str = "plain", label: Callable[[int], str] | None = None,
            reason: str | None = None) -> list[Edit]:
    """The `Edit`s that turn the face multiset of `before` into that of `after`, observed by key.

    `engine` names every edit, except that `label(view id)` (when given) names each REMOVED face's
    engine. `mode="cut"` groups each material's removed and added faces into one cut (the merge);
    `"plain"` gives removes, flips and per-material adds. Order: `"plain"`: removes (by engine, in
    order of first appearance), flips, adds by material; `"cut"`: cuts (or a lone add) by material,
    the removes of materials that gained nothing, then flips.

    Observe-only limits (for K3, which will apply edits instead of recording them):
    - Flipping BOTH members of an opposite-winding coincident pair leaves the key multiset as it
      was, so such a change is invisible here and logs nothing.
    - Keys ignore UVs and normals (K1 `face_keys`: snapped positions, winding and look). When a
      stacked duplicate loses a copy, the copy named removed (the last one) may differ in UV from
      the copy the stage really removed; the multiset is right, the UV of that face may not be."""
    if mode not in ("cut", "plain"):
        raise ValueError(f"unknown mode {mode!r}")
    if before.mesh.materials != after.mesh.materials:
        raise ValueError(f"{stage}: the material list changed, so an edit cannot name its material")
    reason = REASONS.get(stage, stage) if reason is None else reason
    kb, ka = before.keys, after.keys
    cb, ca = Counter(kb), Counter(ka)
    removed_ids = _last_copies(kb, cb - ca)
    added_ids = _last_copies(ka, ca - cb)

    # flips: a removed face whose reversed-winding key is among the added ones
    added_by_key: dict[FaceKey, list[int]] = {}
    for j in added_ids:
        added_by_key.setdefault(ka[j], []).append(j)
    flips, removes = [], []
    for i, rk in zip(removed_ids, _reversed_keys(before, removed_ids)):
        pool = added_by_key.get(rk)
        if rk != kb[i] and pool:
            flips.append((i, rk))
            pool.pop(0)
        else:
            removes.append(i)
    adds = sorted(j for pool in added_by_key.values() for j in pool)

    def evidence(removed_keys, added_keys, material=None) -> dict:
        out = {"stage": stage, "removed_keys": list(removed_keys), "added_keys": list(added_keys)}
        if material is not None:
            out["material"] = int(material)
        return out

    edits: list[Edit] = []
    before_material = before.mesh.face_material[before.mesh_ids(removes)] if removes else []
    after_material = after.mesh.face_material[after.mesh_ids(adds)] if adds else []
    by_material_removed: dict[int, list[int]] = {}
    for i, m in zip(removes, np.asarray(before_material).tolist()):
        by_material_removed.setdefault(int(m), []).append(i)
    by_material_added: dict[int, list[int]] = {}
    for j, m in zip(adds, np.asarray(after_material).tolist()):
        by_material_added.setdefault(int(m), []).append(j)

    def remove_edits(ids: list[int]) -> None:
        groups: dict[str, list[int]] = {}
        for i in ids:
            groups.setdefault(engine if label is None else label(i), []).append(i)
        for name, group in groups.items():
            edits.append(Edit(engine=name, kind="remove", faces=tuple(group), new_faces=None,
                              new_points=None, site=site, reason=reason,
                              evidence=evidence([kb[i] for i in group], [])))

    def add_edit(kind: str, material: int, faces: list[int], ids: list[int]) -> None:
        new_faces, new_points = _new_faces(before, after, ids, stage)
        uv, normal = _corner_values(after, ids)
        edits.append(Edit(engine=engine, kind=kind, faces=tuple(faces), new_faces=new_faces,
                          new_points=new_points, site=site, reason=reason,
                          evidence=evidence([kb[i] for i in faces], [ka[j] for j in ids], material),
                          new_face_uv=uv, new_face_normal=normal))

    if mode == "cut":
        leftover = []
        for material in sorted(set(by_material_removed) | set(by_material_added)):
            gone = by_material_removed.get(material, [])
            new = by_material_added.get(material, [])
            if gone and new:
                add_edit("cut", material, gone, new)
            elif new:
                add_edit("add", material, [], new)
            else:
                leftover += gone
        remove_edits(sorted(leftover))
    else:
        remove_edits(removes)
    if flips:
        edits.append(Edit(engine=engine, kind="flip", faces=tuple(i for i, _ in flips),
                          new_faces=None, new_points=None, site=site, reason=reason,
                          evidence=evidence([kb[i] for i, _ in flips], [rk for _, rk in flips])))
    if mode != "cut":
        for material in sorted(by_material_added):
            add_edit("add", material, [], by_material_added[material])
    return edits


@dataclass
class StageRecord:
    stage: str
    engine: str
    before: FaceView
    after: FaceView
    edits: list[Edit]


class LegacyRun:
    """One `fix_object` run, stage by stage: the shared `FixState`, the face set the last stage
    left, and the record of every stage run so far."""

    def __init__(self, mesh: MeshData, flatness: dict[str, float], profile: FixProfile,
                 looks: dict[int, str]):
        self.looks = looks
        self.state: FixState = start_fix(mesh, flatness, profile)
        self.stages: list[StageRecord] = []
        self._keys_of: dict[int, tuple[MeshData, list[FaceKey]]] = {}
        self.current = self.view(mesh)

    def view(self, mesh: MeshData, ids: np.ndarray | None = None) -> FaceView:
        """A view of `mesh`, sharing the keys already computed for that very mesh object."""
        known = self._keys_of.get(id(mesh))
        view = FaceView(mesh, ids, self.looks, known[1] if known and known[0] is mesh else None)
        self._keys_of[id(mesh)] = (mesh, view.mesh_keys())
        return view

    def output(self, stage: str) -> FaceView:
        """The face set `stage` hands on (the stage has run)."""
        s = self.state
        if stage == "solidify":
            return self.view(s.mesh)
        if stage == "hidden":
            return self.view(s.mesh, np.flatnonzero(~np.asarray(s.removed_pass1, bool)))
        mesh = {"slit": s.mesh_removed, "fragments": s.mesh_fragments,
                "orientation": s.mesh_flipped, "overlap": s.mesh_overlapped,
                "merge": s.final_mesh}[stage]
        return self.view(mesh)


@dataclass
class LegacyEngine:
    """A `RepairEngine` that runs one `fix_object` stage unchanged and returns the edits observed.

    `plan()` RUNS the stage as a side effect: it advances the shared `LegacyRun` state, so calling
    it twice runs the stage twice. That is the observe-only kernel's shortcut, not the protocol's
    meaning (an engine plans; `apply_edits` performs). K3 must split running from planning."""
    name: str
    stage: str
    site: int
    run: LegacyRun = field(repr=False)

    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]:
        run = self.run
        before = run.current
        run.state = dict(FIX_STAGES)[self.stage](run.state)
        after = run.output(self.stage)
        label = None
        if self.stage == "hidden":
            ok = np.asarray(run.state.topo.ok, bool)
            ids = before.ids

            def label(i: int) -> str:
                face = i if ids is None else int(ids[i])
                return "E3" if ok[face] else "E1"
        edits = observe(before, after, stage=self.stage, site=self.site,
                        engine=self.name.split("+")[0], label=label,
                        mode="cut" if self.stage == "merge" else "plain")
        run.current = after
        run.stages.append(StageRecord(self.stage, self.name, before, after, edits))
        return edits


def legacy_engines(run: LegacyRun) -> list[LegacyEngine]:
    """The seven legacy engines, in `fix_object`'s stage order, sharing `run`."""
    return [LegacyEngine(name, stage, site, run)
            for site, (stage, name) in enumerate(STAGE_ENGINES)]
