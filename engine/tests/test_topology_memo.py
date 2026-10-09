"""P1-S2: `analyse_topology` is reused where its input is truly the same, and only there.

The memo is keyed by the mesh's CONTENT (every array `analyse_topology` reads), the flat-material
set and the two dihedral thresholds, so a changed mesh is never served an old topology."""
from dataclasses import replace

import numpy as np
import pytest

import engine.pipeline as pipe
from engine.pipeline import analyse_topology, analyse_topology_memo, clear_topology_memo
from engine.tests.fixtures.build import box_with_partition, cube, grid_slab


@pytest.fixture(autouse=True)
def _fresh_memo():
    clear_topology_memo()
    yield
    clear_topology_memo()


@pytest.fixture
def counted(monkeypatch):
    """Count the real `analyse_topology` computations the memo triggers."""
    calls = []
    real = pipe.analyse_topology

    def counting(mesh, flat_materials=frozenset(), **kw):
        calls.append((mesh.n_faces, frozenset(flat_materials), kw))
        return real(mesh, flat_materials, **kw)

    monkeypatch.setattr(pipe, "analyse_topology", counting)
    return calls


def _same_topology(a, b):
    for name in ("positions_w", "face_w", "ok", "quanta", "face_region", "edge_class"):
        x, y = getattr(a, name), getattr(b, name)
        assert x.dtype == y.dtype and x.shape == y.shape and x.tobytes() == y.tobytes(), name
    assert np.array_equal(np.asarray(a.table.edges), np.asarray(b.table.edges))
    assert a.t_vertices == b.t_vertices
    assert (a.coplanar_angle, a.soft_angle) == (b.coplanar_angle, b.soft_angle)


def _copy(mesh):
    """The same content in new objects: identity must not matter."""
    return replace(mesh, positions=mesh.positions.copy(), uvs=mesh.uvs.copy(), face_v=mesh.face_v.copy(),
                   face_vt=mesh.face_vt.copy(), face_material=mesh.face_material.copy())


def test_same_content_is_computed_once(counted):
    m = box_with_partition()
    first = analyse_topology_memo(m, frozenset({0}))
    second = analyse_topology_memo(_copy(m), frozenset({0}))
    assert len(counted) == 1
    assert second is first
    _same_topology(second, analyse_topology(_copy(m), frozenset({0})))


def test_mutated_vertex_is_recomputed(counted):
    m = box_with_partition()
    old = analyse_topology_memo(m)
    moved = _copy(m)
    moved.positions[0, 0] += 3.0                    # one vertex moves
    new = analyse_topology_memo(moved)
    assert len(counted) == 2
    assert new is not old
    assert not np.array_equal(new.positions_w, old.positions_w)
    _same_topology(new, analyse_topology(moved))


def test_mutating_the_same_object_in_place_is_recomputed(counted):
    """The key is the content, not the object: the very same MeshData, edited, is a new input."""
    m = box_with_partition()
    old = analyse_topology_memo(m)
    m.positions[0, 0] += 3.0
    new = analyse_topology_memo(m)
    assert len(counted) == 2 and new is not old
    _same_topology(new, analyse_topology(m))


@pytest.mark.parametrize("change", ["face_v", "face_material", "uv", "face_vt", "coord_decimals",
                                    "sig_digits"])
def test_every_array_analyse_topology_reads_is_in_the_key(counted, change):
    m = grid_slab(4, 4)
    analyse_topology_memo(m)
    other = _copy(m)
    if change == "face_v":
        other.face_v[[0, 1]] = other.face_v[[1, 0]]
    elif change == "face_material":
        other.materials = ["m0", "m1"]
        other.face_material[0] = 1
    elif change == "uv":
        other.uvs[0, 0] += 0.5
    elif change == "face_vt":
        other.face_vt[[0, 1]] = other.face_vt[[1, 0]]
    elif change == "coord_decimals":
        other = replace(other, coord_decimals=other.coord_decimals + 1)
    elif change == "sig_digits":
        other = replace(other, sig_digits=other.sig_digits + 1)
    analyse_topology_memo(other)
    assert len(counted) == 2


def test_flat_materials_and_angles_are_part_of_the_key(counted):
    m = box_with_partition()
    analyse_topology_memo(m, frozenset())
    analyse_topology_memo(m, frozenset({0}))
    analyse_topology_memo(m, frozenset({0}), coplanar_angle=2.0)
    analyse_topology_memo(m, frozenset({0}), soft_angle=7.0)
    assert len(counted) == 4
    analyse_topology_memo(m, frozenset({0}))                      # all four are now cached
    analyse_topology_memo(m, [0])                                  # a list of the same ints: the same set
    assert len(counted) == 4


def test_default_angles_equal_the_explicit_defaults(counted):
    m = cube(10.0)
    a = analyse_topology_memo(m)
    b = analyse_topology_memo(m, coplanar_angle=pipe.COPLANAR_ANGLE, soft_angle=pipe.SOFT_ANGLE)
    assert a is b and len(counted) == 1


def test_bad_flat_materials_still_raise():
    with pytest.raises(TypeError):
        analyse_topology_memo(cube(10.0), frozenset({"m0"}))


def test_memo_is_bounded(counted):
    meshes = []
    for i in range(pipe.TOPOLOGY_MEMO_SIZE + 2):
        m = cube(10.0 + i)
        meshes.append(m)
        analyse_topology_memo(m)
    n = len(counted)
    analyse_topology_memo(meshes[-1])                              # newest is still held
    assert len(counted) == n
    analyse_topology_memo(meshes[0])                               # oldest was evicted
    assert len(counted) == n + 1


def test_clear_drops_everything(counted):
    m = cube(10.0)
    analyse_topology_memo(m)
    clear_topology_memo()
    analyse_topology_memo(m)
    assert len(counted) == 2


# ------------------------------------------------------------------ through the fix pipeline
import engine.fixes.pipeline as fix_pipeline
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import slab_with_wall

_FAST = FixProfile(guard_size=(120, 80), n_dirs=32)


def _unmemoised(monkeypatch, record):
    """Make the fix pipeline recompute every topology, recording the meshes it asked for."""
    real = pipe.analyse_topology

    def fresh(mesh, flat_materials=frozenset(), **kw):
        record.append(pipe._topology_key(mesh, flat_materials, kw["coplanar_angle"], kw["soft_angle"]))
        return real(mesh, flat_materials, **kw)

    monkeypatch.setattr(fix_pipeline, "analyse_topology_memo", fresh)


@pytest.mark.parametrize("make", [box_with_partition, slab_with_wall], ids=["partition", "wall"])
def test_fix_object_computes_each_distinct_input_once_with_identical_results(monkeypatch, make):
    base_keys = []
    _unmemoised(monkeypatch, base_keys)
    clear_topology_memo()
    base = fix_object(make(), {}, _FAST)
    monkeypatch.undo()
    clear_topology_memo()

    calls = []
    real = pipe.analyse_topology
    monkeypatch.setattr(pipe, "analyse_topology",
                        lambda mesh, flat_materials=frozenset(), **kw: (calls.append(1),
                                                                        real(mesh, flat_materials, **kw))[1])
    memo = fix_object(make(), {}, _FAST)

    assert len(base_keys) == 4                                  # the four stage inputs, unmemoised
    assert len(calls) == len(set(base_keys))                    # memo: one compute per distinct input
    assert len(calls) < len(base_keys)                          # and the fixture does repeat one
    for name in ("positions", "face_v", "face_vt", "face_material"):
        assert np.array_equal(getattr(memo.mesh, name), getattr(base.mesh, name)), name
    assert np.array_equal(memo.face_region_final, base.face_region_final)
    assert repr(memo.rings) == repr(base.rings)
    assert np.array_equal(memo.exposure_class, base.exposure_class)
    assert memo.guard_final.totals == base.guard_final.totals


def test_the_references_topology_is_served_to_the_cli(counted):
    """`cmd_fix` / `cmd_preview_data` ask for the reference mesh's topology after `fix_object`
    returns: it is the one `stage_hidden` already computed, so it costs nothing."""
    from engine.pipeline import flat_material_indices
    mesh = box_with_partition()
    result = fix_object(mesh, {}, _FAST)
    n = len(counted)
    flat = flat_material_indices(mesh, {}, _FAST.flat_texture_std)
    analyse_topology_memo(result.reference_mesh, flat)
    assert len(counted) == n
