"""load_targets refuses a file of the wrong shape with a ValueError (P1-H1 item 10), which the CLI turns into exit 2."""
from __future__ import annotations

import json

import pytest

from engine.validate.checks import load_targets


def _write(tmp_path, value):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize("value", [[], [1, 2], "signed", 7, None, True])
def test_a_file_that_is_not_an_object_is_a_value_error(tmp_path, value):
    with pytest.raises(ValueError, match="object"):
        load_targets(_write(tmp_path, value))


@pytest.mark.parametrize("kinds", [[], ["flicker_diff"], "hidden", 3, None])
def test_kinds_that_is_not_an_object_is_a_value_error(tmp_path, kinds):
    with pytest.raises(ValueError, match="kinds"):
        load_targets(_write(tmp_path, {"signed": True, "kinds": kinds}))


def test_a_file_without_kinds_and_an_empty_kinds_still_load(tmp_path):
    assert load_targets(_write(tmp_path, {"signed": False})) == {"signed": False}
    assert load_targets(_write(tmp_path, {"signed": True, "kinds": {}}))["kinds"] == {}


def test_the_signed_file_still_loads_and_unknown_kinds_still_refuse(tmp_path):
    assert load_targets()["signed"] is True
    with pytest.raises(ValueError, match="unknown kinds"):
        load_targets(_write(tmp_path, {"signed": True, "kinds": {"flickr_diff": 0}}))
