"""Job P2-H2 item 6: static checks on `tools/sketchup/needs_modelling_views.rb`."""
from __future__ import annotations

import re
from pathlib import Path

from tools.tests.test_needs_modelling_views import SCRIPT, _code


def test_the_script_never_calls_offset_with_a_negative_length():
    assert not re.search(r"\.offset\([^)]*,\s*-", _code())


def test_no_line_has_two_string_literals_separated_by_five_or_more_spaces():
    for line_no, line in enumerate(SCRIPT.read_text(encoding="utf-8").splitlines(), start=1):
        assert not re.search(r"['\"][ ]{5,}['\"]", line), f"line {line_no}: {line!r}"
