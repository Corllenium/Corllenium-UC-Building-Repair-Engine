import pytest

from engine.pipeline import FLAT_TEXTURE_STD, analyse_topology, flat_material_indices
from engine.tests.fixtures.build import cube


def _mesh_with_materials(names):
    m = cube(10.0)
    m.materials = list(names)
    return m


def test_flat_material_indices_maps_names_to_indices():
    m = _mesh_with_materials(["stone", "paint", "brick"])
    flatness = {"stone": 40.0, "brick": 2.0}
    assert flat_material_indices(m, flatness) == frozenset({1, 2})


def test_untextured_material_with_no_flatness_entry_is_flat():
    m = _mesh_with_materials(["plain"])
    assert flat_material_indices(m, {}) == frozenset({0})


def test_patterned_material_above_threshold_is_not_flat():
    m = _mesh_with_materials(["pattern"])
    assert FLAT_TEXTURE_STD == 8.0
    assert flat_material_indices(m, {"pattern": 120.0}) == frozenset()


def test_analyse_topology_raises_type_error_on_material_name_in_flat_materials():
    m = cube(10.0)
    with pytest.raises(TypeError):
        analyse_topology(m, flat_materials=frozenset({"m0"}))
