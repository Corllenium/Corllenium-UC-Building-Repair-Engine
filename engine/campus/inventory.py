"""Campus inventory (spec 2026-10-03, P0 task 10): buildings, a level table per building, floor and element
units, duplicate groups, misnamed and missing levels. Everything is a draft for the owner to confirm; nothing
here writes geometry.
"""
from __future__ import annotations

import re

# The brief's prefix table, verbatim. A name belongs to the building whose prefix it starts with, followed
# by an underscore or the end of the name; matching ignores case and the longest prefix wins (so
# `Main_Infrustructure_*` is MAIN_INFRA, not MAIN).
PREFIX_TABLE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("CHTM", "Chtm", "chtm"), "CHTM"),
    (("EDS", "Eds"), "EDS"),
    (("BRS",), "BRS"),
    (("Gymnasium",), "GYMNASIUM"),
    (("Main_Infrustructure",), "MAIN_INFRA"),
    (("MAIN", "Main"), "MAIN"),
    (("PE",), "PE"),
    (("Sciene_A",), "SCIENCE_A"),
    (("Architecture", "ARCHITECTURE"), "ARCHITECTURE"),
)
SITE = "SITE"

_PREFIXES = sorted(((p.casefold(), b) for ps, b in PREFIX_TABLE for p in ps), key=lambda pb: -len(pb[0]))


def building_of(name: str) -> str:
    """The building a split name belongs to (SITE when no prefix matches)."""
    low = name.casefold()
    for prefix, building in _PREFIXES:
        if low == prefix or low.startswith(prefix + "_"):
            return building
    return SITE


# `1st`, `2nd`, `3RD`, `4th`, and the owner's `5ft` / `6ft` typos for `5th` / `6th`.
_ORDINAL = re.compile(r"(?<![A-Za-z0-9])(\d{1,2})(?:st|nd|rd|th|ft)(?![A-Za-z])", re.I)
# `Floor 4`, `Floor_4`, `Floor_plan_2`, `plan 2`.
_PLAN = re.compile(r"(?:floor|plan)[ _]*(\d{1,2})(?!\d)", re.I)


def floor_number(name: str) -> int | None:
    """The floor number a group's name claims, or None."""
    m = _ORDINAL.search(name) or _PLAN.search(name)
    return int(m.group(1)) if m else None
