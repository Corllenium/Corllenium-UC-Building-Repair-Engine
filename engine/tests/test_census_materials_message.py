"""One missing-materials message (P1-H1 item 11): both say "Materials map not found", show the resolved path and tell
the reader to pass --materials."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.campus.census import flicker_split
from engine.detectors.errors import find_errors
from engine.tests.fixtures.build import two_sided_wall


def _mesh_pairs():
    mesh = two_sided_wall()
    return mesh, find_errors(mesh)["flicker_pairs"]


def test_a_named_map_that_is_missing_shows_its_resolved_path_and_says_pass_materials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mesh, pairs = _mesh_pairs()
    with pytest.raises(FileNotFoundError) as info:
        flicker_split(mesh, pairs, materials=Path("nope") / "m.json")
    text = str(info.value)
    assert text.startswith("Materials map not found") and str((tmp_path / "nope" / "m.json").resolve()) in text
    assert "--materials" in text


def test_the_default_map_that_is_missing_says_the_same(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)               # no data/campus/materials.json here
    mesh, pairs = _mesh_pairs()
    with pytest.raises(FileNotFoundError) as info:
        flicker_split(mesh, pairs)
    text = str(info.value)
    assert text.startswith("Materials map not found")
    assert str((tmp_path / "data" / "campus" / "materials.json").resolve()) in text
    assert "--materials" in text
