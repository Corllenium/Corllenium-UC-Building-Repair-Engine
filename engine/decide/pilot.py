"""The Jev pilot: how good are Jev's soft answers on the campus' 85 group names and 391 materials?

Ground truth is `data/campus/campus_map.json` (owner-confirmed, P0-13), never Jev itself:
- building: the building whose `groups` list holds the group, else SITE;
- unit type: the `type` of the group's single unit (floor / element / site), unknown when the group is in no
  unit or in several; compared in three coarse classes (see `TYPE_CLASSES`);
- floor: the unit's level (`L05` -> 5), only for a single floor unit;
- duplicate copy: the group is in `excluded`.

Only text goes to Jev: names, small numbers, texture file names. The OBJ files are read here only for the
bounding box of the vertices; nothing of them is sent.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Callable

# `_union_overlap` is private but is the inventory's own footprint measure; reusing it keeps the hint identical
# to the inventory's "mostly in another building" test instead of a second, slightly different copy.
from engine.campus.inventory import SITE, _union_overlap, building_of
from engine.decide.jev import MODEL, JevDecider, classify_group_names, classify_materials

#: Which Jev unit types count as right for each campus-map unit type.
TYPE_CLASSES: dict[str, set[str]] = {
    "floor": {"floor"},
    "element": {"stair", "roof", "shell", "other"},
    "site": {"road", "landscape", "bridge", "other"},
}
FOOTPRINT_FRAC = 0.5      # the inventory's own "mostly in another building" fraction
SPOT_CHECK = 30


TYPE_NOTE = ("type is the lenient figure: 'other' counts as right for both element and site, which inflates it. "
             "type_strict is floor vs non-floor only (a floor must be answered 'floor', anything else must not be).")
HINT_NOTE = ("footprint_building is a hint given to Jev in the building question (from the XY boxes of the other "
             "groups, assigned by the inventory's name table); building accuracy is therefore 'Jev plus hint'. "
             "jev_agrees counts answered rows where Jev's building equals the hint; hint_correct counts rows "
             "where the hint itself equals the truth.")


def type_matches(truth_class: str, answer: str | None) -> bool:
    return answer in TYPE_CLASSES.get(truth_class, set())


# ------------------------------------------------------------------------------------------ truth


def load_truth(campus_map: dict, groups: list[str]) -> dict[str, dict]:
    """`{group: {"building", "type", "floor", "duplicate"}}`; None marks a field whose truth is unknown."""
    building = {}
    for key, info in campus_map.get("buildings", {}).items():
        for g in info.get("groups", []):
            building[g] = key
    units: dict[str, list[dict]] = {}
    for u in campus_map.get("units", []):
        for m in u.get("members", []):
            units.setdefault(m["group"], []).append(u)
    excluded = {e["group"] for e in campus_map.get("excluded", [])}
    truth = {}
    for g in groups:
        us = units.get(g, [])
        one = us[0] if len(us) == 1 else None
        floor = None
        if one is not None and one.get("type") == "floor":
            m = re.fullmatch(r"L(\d+)", str(one.get("level") or ""))
            floor = int(m.group(1)) if m else None
        truth[g] = {"building": building.get(g, SITE), "type": one.get("type") if one else None,
                    "floor": floor, "duplicate": g in excluded}
    return truth


# ------------------------------------------------------------------------------------------ rows


def _obj_bbox(path: Path) -> tuple[float, float, float, float, float, float] | None:
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    seen = False
    with open(path, "rb") as fh:
        for line in fh:
            if line[:2] != b"v ":
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            for i in range(3):
                x = float(parts[i + 1])
                if x < lo[i]:
                    lo[i] = x
                if x > hi[i]:
                    hi[i] = x
            seen = True
    return (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]) if seen else None


def group_rows(source: dict) -> list[dict]:
    """`{"name", "tris", "z_min", "z_max", "footprint_building"}` per group in `source.json`'s manifest.
    `footprint_building` is the building (by the inventory's name table, the group itself left out) whose
    group boxes cover more than half of this group's XY box, or None."""
    snaps = {s["group"]: s for s in source.get("snapshots", [])}
    boxes: dict[str, tuple] = {}
    tris: dict[str, int] = {}
    for m in source["manifest"]:
        name = m["group"]
        tris[name] = int(m.get("tris", 0))
        s = snaps.get(name)
        box = _obj_bbox(Path(s["dir"]) / s["file"]) if s else None
        if box is not None:
            boxes[name] = box
    rows = []
    for m in source["manifest"]:
        name = m["group"]
        box = boxes.get(name)
        footprint = None
        if box is not None:
            rect = (box[0], box[1], box[3], box[4])
            area = (rect[2] - rect[0]) * (rect[3] - rect[1])
            if area > 0:
                best, which = 0.0, None
                for b in {building_of(o) for o in boxes if o != name} - {SITE}:
                    others = [(boxes[o][0], boxes[o][1], boxes[o][3], boxes[o][4])
                              for o in boxes if o != name and building_of(o) == b]
                    frac = _union_overlap(rect, others) / area
                    if frac > best:
                        best, which = frac, b
                if best >= FOOTPRINT_FRAC:
                    footprint = which
        rows.append({"name": name, "tris": tris[name], "z_min": box[2] if box else None,
                     "z_max": box[5] if box else None, "footprint_building": footprint})
    return rows


# ------------------------------------------------------------------------------------------ scoring


def score(pairs: list, matches: Callable) -> dict:
    """`pairs`: (Decision, truth) with truth None when unknown. `accuracy`: right among the answered;
    `coverage`: accepted (confidence at or above the gate) among rows with a known truth;
    `accuracy_within_coverage`: right among the accepted."""
    known = [(d, t) for d, t in pairs if t is not None]
    answered = [(d, t) for d, t in known if d.source == "jev"]
    accepted = [(d, t) for d, t in answered if d.accepted]
    right = sum(1 for d, t in answered if matches(d.answer, t))
    right_accepted = sum(1 for d, t in accepted if matches(d.answer, t))
    return {
        "n": len(pairs), "n_truth": len(known), "unknown_truth": len(pairs) - len(known),
        "answered": len(answered), "correct": right, "accepted": len(accepted), "accepted_correct": right_accepted,
        "accuracy": right / len(answered) if answered else None,
        "coverage": len(accepted) / len(known) if known else None,
        "accuracy_within_coverage": right_accepted / len(accepted) if accepted else None,
    }


def hint_summary(rows: list[dict], results: list[dict], truth: dict) -> dict:
    """How often a group has a footprint hint, how often Jev's building equals it, how often it is right."""
    hint = {r["name"]: r["footprint_building"] for r in rows}
    with_hint = [r for r in results if hint[r["name"]] is not None]
    return {
        "with_hint": len(with_hint),
        "jev_agrees": sum(1 for r in with_hint if r["building"].source == "jev" and r["building"].answer == hint[r["name"]]),
        "hint_correct": sum(1 for r in with_hint if hint[r["name"]] == truth[r["name"]]["building"]),
        "note": HINT_NOTE,
    }


def _sources(decisions) -> dict:
    return dict(Counter(d.source for d in decisions))


def _dec(d) -> dict:
    return {"answer": d.answer, "confidence": d.confidence, "source": d.source, "accepted": d.accepted}


# ------------------------------------------------------------------------------------------ the run


def run_pilot(source_path, materials_path, map_path, out_path, decider: JevDecider) -> dict:
    source = json.loads(Path(source_path).read_text(encoding="utf-8"))
    campus_map = json.loads(Path(map_path).read_text(encoding="utf-8"))
    materials = json.loads(Path(materials_path).read_text(encoding="utf-8"))["materials"]

    t0 = time.perf_counter()
    rows = group_rows(source)
    truth = load_truth(campus_map, [r["name"] for r in rows])
    results = classify_group_names(rows, decider)
    hints = {r["name"]: r["footprint_building"] for r in rows}
    pairs = {k: [(r[k], truth[r["name"]][k]) for r in results] for k in ("building", "type", "floor", "duplicate")}
    groups = {
        "n": len(rows),
        "sources": _sources(d for r in results for d in (r["building"], r["type"], r["floor"], r["duplicate"])),
        "building": score(pairs["building"], lambda a, t: a == t),
        "type": score(pairs["type"], lambda a, t: type_matches(t, a)),
        "type_strict": score(pairs["type"], lambda a, t: (a == "floor") == (t == "floor")),
        "type_note": TYPE_NOTE,
        "building_hint": hint_summary(rows, results, truth),
        "floor": score(pairs["floor"], lambda a, t: a is not None and int(round(a)) == t),
        "duplicate": score(pairs["duplicate"], lambda a, t: a == t),
        "rows": [{"name": r["name"], "footprint_building": hints[r["name"]], "truth": truth[r["name"]],
                  **{k: _dec(r[k]) for k in ("building", "type", "floor", "duplicate")}} for r in results],
    }

    names = sorted(materials)
    items = []
    for n in names:
        m = materials[n]
        tex = Path(m["map_kd"]).name if m.get("map_kd") else None
        items.append({"name": n, "texture": tex, "kd": m.get("kd")})
    mres = classify_materials(items, decider)
    step = max(1, len(names)) / SPOT_CHECK
    spot = [{"name": mres[i]["name"], "texture": items[i]["texture"], "kd": items[i]["kd"],
             "category": mres[i]["category"].answer, "confidence": mres[i]["category"].confidence,
             "accepted": mres[i]["category"].accepted, "trim": mres[i]["trim"].answer}
            for i in sorted({int(k * step) for k in range(SPOT_CHECK)} if names else [])]
    materials_report = {
        "n": len(names),
        "sources": _sources(d for r in mres for d in (r["category"], r["trim"])),
        "histogram": dict(Counter(r["category"].answer for r in mres if r["category"].source == "jev")),
        "histogram_accepted": dict(Counter(r["category"].answer for r in mres if r["category"].accepted)),
        "trim_yes_accepted": sum(1 for r in mres if r["trim"].accepted and r["trim"].answer is True),
        "spot_check": spot,
    }

    ok = [c for c in decider.calls if c.get("ok")]
    lat = [c["latency_s"] for c in decider.calls]
    calls = {
        "n": len(decider.calls), "failed": len(decider.calls) - len(ok),
        "latency_mean_s": sum(lat) / len(lat) if lat else None, "latency_max_s": max(lat) if lat else None,
        "input_tokens": sum(c["input_tokens"] or 0 for c in ok), "output_tokens": sum(c["output_tokens"] or 0 for c in ok),
        "models": sorted({c["model"] for c in ok if c.get("model")}),
        "per_call": decider.calls,
    }
    report = {
        "model": decider.model if decider.model else MODEL, "available": decider.available,
        "min_confidence": decider.min_confidence, "batch": decider.batch,
        "truth": "data/campus/campus_map.json (owner-confirmed); type compared in coarse classes " +
                 json.dumps({k: sorted(v) for k, v in TYPE_CLASSES.items()}),
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "groups": groups, "materials": materials_report, "calls": calls,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    os.replace(tmp, out_path)
    return json.loads(out_path.read_text(encoding="utf-8"))
