"""Job P2-K0 item 3: only E8 may add faces (AGENTS.md section 4: generic hole filling is blocked; E8's narrow flat
fill is the one exception). A non-legacy `add` from any other engine is refused; a `cut` stays allowed; the legacy
observer keeps its E7 adds behind the explicit `Edit.legacy` marker, set only by `engine/repair/engines/legacy.py`.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from engine.repair.types import Edit


def _add(engine, **kw):
    return Edit(engine=engine, kind="add", faces=(), new_faces=np.array([[0, 1, 2]]), new_points=None, site=0,
                reason="r", evidence={"material": 0}, **kw)


@pytest.mark.parametrize("engine", ["E1", "E2", "E3", "E4", "E5", "E6", "E7"])
def test_a_non_legacy_add_from_any_engine_but_e8_is_refused(engine):
    with pytest.raises(ValueError, match="add"):
        _add(engine)


def test_an_e8_add_is_accepted():
    assert _add("E8").kind == "add"


@pytest.mark.parametrize("engine", ["E5", "E7"])
def test_a_cut_stays_allowed_for_other_engines(engine):
    edit = Edit(engine=engine, kind="cut", faces=(0,), new_faces=np.array([[0, 1, 2]]), new_points=None, site=0,
                reason="r", evidence={})
    assert edit.kind == "cut"


@pytest.mark.parametrize("engine", ["E5", "E7", "E8"])
def test_the_legacy_marker_lets_an_observed_add_through(engine):
    assert _add(engine, legacy=True).legacy is True


def test_an_edit_is_not_legacy_unless_it_says_so():
    assert _add("E8").legacy is False


def test_only_the_legacy_engine_module_sets_the_legacy_marker():
    root = pathlib.Path(__file__).resolve().parents[1]
    setters = sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*.py")
                     if "tests" not in p.parts and "legacy=True" in p.read_text(encoding="utf-8"))
    assert setters == ["repair/engines/legacy.py"]
