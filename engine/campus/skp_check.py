"""Does the CHECKPOINT-17 OBJ export match the owner's CHECKPOINT-17 backup? (P0 task 11)

The owner's backup `.skp` is the source of truth; the OBJ files that every later step works on were
exported from it and frozen by `engine.campus.source` (`data/campus/source.json`). This is the
read-only proof that the export says what the backup says: the backup is opened through
SketchUp's own C API (`engine.io.skp_reader`, which cannot save), and for every split file of the
export the bounding box and the face area of what the backup holds for it are compared.

WHICH FACES ARE A FILE'S. The split files are the owner's: `split_named.py` cut the one OBJ that
SketchUp wrote into a file per SketchUp group, by this rule, which `split_key` repeats on the
backup's own groups:
* a face's ancestors are the groups above the group that holds it (that group itself is not
  looked at: SketchUp's exporter puts a name of its own in its place);
* names the Minecraft import made (`Group12`, `Mesh3`, `minecraft_*`, `littletiles_*`, ...) are
  not names a person gave, and are skipped;
* the file is named by the OUTERMOST ancestor whose name says floor, side walk, stair, bridge,
  roof, pathway or ground; with none, by the outermost named ancestor; with no named ancestor
  at all, by the outermost one, and with no ancestor at all, `unnamed`.
So the faces of a building group are in its file only if no floor-like group inside it took them:
the file of `MAIN BUILDING` does not hold the floors cut out of it. A file's *unit* is the one
group that gives it its name, with every face that goes to it.

NAMES. SketchUp's exporter writes every character that is not a letter, digit or underscore as
`_`, so the group `Eds 2nd Floor.obj` is the file `Eds_2nd_Floor_obj`. Two groups with one name
get one key and two units (the exporter numbers the second file: `..._obj1`), and the number
the exporter gives a nameless group (`Group137`) cannot be told from the backup; both are
*families* of files and units, told apart only by their shape (see `compare`).
"""
from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from engine.io import skp_reader
from engine.io.obj_reader import read_obj
from engine.io.snapshot import copy_verified, sha256_file

#: How long the child process that reads the backup may run before it is killed.
WALK_TIMEOUT_S = 30 * 60
#: The walk is not started with less commit memory than this free (MB). Measured on this machine,
#: 2026-10-03: loading the 150 MB backup takes 1.97 GB of commit and the walk peaks at 2.5 GB, and
#: the machine ran at 93-96 % of its commit limit, where one more allocation that fails stops
#: Unity and Docker, not only this run. The margin keeps about 1 GB for everyone else.
MIN_FREE_COMMIT_MB = 3500


class BackupMismatch(Exception):
    """The copy of the backup is not the file `source.json` froze: it changed since the freeze."""


class WalkFailed(Exception):
    """The child process that reads the backup failed, timed out, or wrote nothing."""


class NotEnoughMemory(WalkFailed):
    """The machine has too little commit memory left to start the walk."""


#: A file's bounding box must agree with the backup's to within 2 x the export's print step, and
#: its face area to within this fraction. The step is measured (`print_step`): 0.1 in.
AREA_TOL = 0.005
#: Looser limits for telling the members of a family apart by their shape (`compare`): a pairing
#: is made only when every pair is this close, and only when the next best pairing is clearly worse.
PAIR_BBOX_TOL = 5.0
PAIR_AREA_TOL = 0.05
PAIR_MARGIN = 3.0
#: The largest family whose pairings are all tried (n! of them).
MAX_FAMILY = 6
#: The bounds of a box, in the order `bbox_dev` lists them.
BOUNDS = ("min x", "min y", "min z", "max x", "max y", "max z")

#: Names the Minecraft import made, not names a person gave (the owner's `split_named.py`).
AUTO = re.compile(r"^(Group|Mesh|Component)\d*$"
                  r"|^(minecraft|littletiles|kirosblocks|mumi|Color|Material)[_A-Za-z0-9]*$", re.I)
#: Words that make a group a floor-like thing worth a file of its own (the same script).
KEY = re.compile(r"floor|side_?walk|stair|bridge|roof|pathway|ground", re.I)
#: What the exporter calls the faces of the model's top level and of its top-level groups.
UNNAMED = "unnamed"
UNNAMED_PATH = "(the model's own faces and those directly in its top-level groups)"


def exporter_name(name: str) -> str:
    """`name` as SketchUp's OBJ exporter writes it: every character that is not an ASCII letter,
    digit or underscore becomes `_`."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def token(node: dict) -> str:
    """What the exporter calls a group or component instance: its own name, else (an instance)
    its definition's name, else a name of the kind it gives a nameless group (`Group<N>`)."""
    raw = node["name"] or (node["definition"] if node["kind"] == "instance" else "") or ""
    return exporter_name(raw) or "Group"


def split_key(chain: list[dict]) -> tuple[str, dict | None]:
    """`(file name, the group that gives it)` for a face in `chain[-1]`, where `chain` runs from
    the outermost group down to the group that holds the face (empty for the model's own faces).
    The rule is in the module docstring."""
    ancestors = [(token(n), n) for n in reversed(chain[:-1])]          # inner -> outer
    named = [(t, n) for t, n in ancestors if not AUTO.match(t)]
    if not named:
        return (ancestors[-1][0], ancestors[-1][1]) if ancestors else (UNNAMED, None)
    floorlike = [(t, n) for t, n in named if KEY.search(t)]
    return floorlike[-1] if floorlike else named[-1]


def _union(a: list | None, b: list | None) -> list | None:
    if a is None or b is None:
        return a or b
    return [[min(p, q) for p, q in zip(a[0], b[0])], [max(p, q) for p, q in zip(a[1], b[1])]]


def sdk_units(walk: dict) -> list[dict]:
    """What the backup holds for each file, from `walk` (`engine.io.skp_reader.walk_skp`): one
    unit per group that gives a file its name, in the order the walk meets them --
    `{"key", "path", "faces", "area", "bbox", "tris"}` with the faces, the area and the box
    (the union of its nodes' boxes) of every face that goes to it. `path` names the group from the
    top of the model down."""
    units: dict[int, dict] = {}

    def add(node: dict, selected: dict | None, key: str, path: list[str]) -> None:
        unit = units.setdefault(id(selected) if selected is not None else 0, {
            "key": key, "path": UNNAMED_PATH if selected is None else " > ".join(path),
            "faces": 0, "area": 0.0, "bbox": None, "tris": 0})
        unit["faces"] += node["faces"]
        unit["tris"] += node["tris"]
        unit["area"] += node["area"]
        unit["bbox"] = _union(unit["bbox"], node["bbox"])

    def visit(node: dict, chain: list[dict]) -> None:
        chain = chain + [node]
        if node["faces"]:
            key, selected = split_key(chain)
            depth = next((i for i, n in enumerate(chain) if n is selected), -1)
            add(node, selected, key, [n["name"] or token(n) for n in chain[:depth + 1]])
        for child in node["children"]:
            visit(child, chain)

    root = walk["root"]
    if root["faces"]:
        add(root, None, UNNAMED, [])
    for child in root["children"]:
        visit(child, [])
    return list(units.values())


# ---------------------------------------------------------------------------- comparing


def print_step(max_abs_coordinate: float, sig_digits: int = 6) -> float:
    """The smallest step the export can show in a coordinate as large as `max_abs_coordinate`:
    SketchUp's OBJ exporter writes `sig_digits` significant digits (`23170.2`, `-1987.03`), so a
    coordinate of 10,000 to 99,999 in moves in steps of 0.1 in, one of 1,000 to 9,999 in 0.01 in."""
    if max_abs_coordinate <= 0:
        return 0.0
    exponent = len(str(int(max_abs_coordinate))) - 1
    return 10.0 ** (exponent - (sig_digits - 1))


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _deviation(export_bbox: list, unit_bbox: list) -> list[float]:
    """The backup's box minus the export's, as `[min x, min y, min z, max x, max y, max z]`."""
    return [u - e for u, e in zip([*unit_bbox[0], *unit_bbox[1]], [*export_bbox[0], *export_bbox[1]])]


def _entry(row: dict, unit: dict, paired_by: str, bbox_tol: float, area_tol: float) -> dict:
    dev = _deviation(row["bbox"], unit["bbox"])
    worst = max(range(6), key=lambda i: abs(dev[i]))
    area_rel = (unit["area"] - row["area"]) / row["area"]
    reasons = []
    if abs(dev[worst]) > bbox_tol:
        both = [*row["bbox"][0], *row["bbox"][1]]
        reasons.append(
            f"bounding box: {BOUNDS[worst]} is {_num(both[worst] + dev[worst])} in the backup and "
            f"{_num(both[worst])} in the export, {_num(abs(dev[worst]))} in apart "
            f"(tolerance {_num(bbox_tol)} in)")
    if abs(area_rel) > area_tol:
        reasons.append(f"area: the backup has {unit['area']:,.1f} sq in and the export "
                       f"{row['area']:,.1f}, {area_rel * 100:+.3f}% (tolerance {area_tol * 100:g}%)")
    return {"name": row["name"], "file": row["file"], "paired_by": paired_by,
            "unit": {k: unit[k] for k in ("key", "path", "faces", "tris", "area", "bbox")},
            "export": {k: row[k] for k in ("tris", "area", "bbox")},
            "bbox_dev": dev, "bbox_max_dev": abs(dev[worst]), "area_rel": area_rel,
            "tris_diff": unit["tris"] - row["tris"],
            "severity": max(abs(dev[worst]) / bbox_tol, abs(area_rel) / area_tol),
            "reasons": reasons}


def family_of(name: str) -> str:
    """`name` without the number the exporter puts on the second of two groups of one name
    (`BRS_4th_floor_obj1`), or on a nameless group (`Group137`)."""
    return re.sub(r"\d+$", "", name) or name


def _distance(row: dict, unit: dict) -> float:
    dev = _deviation(row["bbox"], unit["bbox"])
    extent = max(row["bbox"][1][i] - row["bbox"][0][i] for i in range(3)) or 1.0
    return abs(unit["area"] - row["area"]) / (row["area"] or 1.0) + max(abs(d) for d in dev) / extent


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _pair_by_shape(rows: list[dict], units: list[dict]) -> tuple[list[int] | None, str]:
    """`(for each row the index of its unit, "")` when exactly one pairing of equally many rows and
    units is both close (`PAIR_BBOX_TOL`, `PAIR_AREA_TOL`) and clearly better than any other
    (`PAIR_MARGIN` times closer); otherwise `(None, why not)`."""
    if len(rows) > MAX_FAMILY:
        return None, f"too many to try every pairing ({len(rows)} files)"
    costs = sorted((sum(_distance(rows[i], units[j]) for i, j in enumerate(perm)), perm)
                   for perm in itertools.permutations(range(len(units))))
    best_cost, best = costs[0]
    for i, j in enumerate(best):
        dev = _deviation(rows[i]["bbox"], units[j]["bbox"])
        area_rel = (units[j]["area"] - rows[i]["area"]) / (rows[i]["area"] or 1.0)
        if max(abs(d) for d in dev) > PAIR_BBOX_TOL or abs(area_rel) > PAIR_AREA_TOL:
            return None, (f"no pairing is close enough (every pair must be within "
                          f"{_num(PAIR_BBOX_TOL)} in and {PAIR_AREA_TOL * 100:g}% of area)")
    if costs[1][0] <= PAIR_MARGIN * best_cost + 1e-9:
        return None, "the groups look alike, so no pairing is clearly better than another"
    return list(best), ""


def compare(rows: list[dict], units: list[dict], *, bbox_tol: float, area_tol: float = AREA_TOL) -> dict:
    """Every file of the export (`rows`: `{"name", "file", "tris", "area", "bbox"}`) against what
    the backup holds (`units`, from `sdk_units`):

    * `matches` and `mismatches`: a file and the unit it is paired with -- by `name` (same name),
      `name_family` (one file and one group whose names differ only by the exporter's number) or
      `geometry` (see below) -- with the box deviations, the area difference and, for a mismatch,
      the `reasons`; mismatches worst first;
    * `ambiguities`: every family of several groups or several files of one name, with `resolved`
      true when the files could be paired with the groups by shape alone, and false (the files are
      then in no other list) when they could not;
    * `misses`: files with no group in the backup, `sdk_only`: groups with no file.

    A family is the files and the units whose names differ at most by trailing digits. When it has
    as many files as groups, and exactly one way to pair them is close and clearly better than every
    other, the files are paired that way (`geometry`), since the name cannot say which is which."""
    families: dict[str, dict] = {}
    for r in rows:
        families.setdefault(family_of(r["name"]), {"rows": [], "units": []})["rows"].append(r)
    for u in units:
        families.setdefault(family_of(u["key"]), {"rows": [], "units": []})["units"].append(u)

    entries: dict[str, dict] = {}
    result = {"matches": [], "mismatches": [], "ambiguities": [], "misses": [], "sdk_only": []}
    for family, members in families.items():
        frows, funits = members["rows"], members["units"]
        if not funits:
            for r in frows:
                result["misses"].append({
                    "name": r["name"], "file": r["file"],
                    "reason": f"the backup has no group called {r['name']} (nor one numbered like it)",
                    "export": {k: r[k] for k in ("tris", "area", "bbox")}})
            continue
        if not frows:
            for u in funits:
                result["sdk_only"].append({
                    **{k: u[k] for k in ("key", "path", "faces", "tris", "area", "bbox")},
                    "reason": "the backup has faces here and the export has no file for them"})
            continue
        if len(frows) == 1 and len(funits) == 1:
            how = "name" if frows[0]["name"] == funits[0]["key"] else "name_family"
            entries[frows[0]["name"]] = _entry(frows[0], funits[0], how, bbox_tol, area_tol)
            continue
        counts = f"{_plural(len(funits), 'group')} of the backup are called like this and the export " \
                 f"has {_plural(len(frows), 'file')} for them"
        ambiguity = {"family": family, "rows": [r["name"] for r in frows],
                     "files": [{k: r[k] for k in ("name", "file", "tris", "area", "bbox")} for r in frows],
                     "units": funits, "resolved": False, "reason": counts}
        result["ambiguities"].append(ambiguity)
        if len(frows) != len(funits):
            continue
        pairing, why = _pair_by_shape(frows, funits)
        if pairing is None:
            ambiguity["reason"] = f"{counts}; {why}"
            continue
        ambiguity["resolved"] = True
        ambiguity["reason"] = f"{counts}; paired by shape"
        for i, j in enumerate(pairing):
            entries[frows[i]["name"]] = _entry(frows[i], funits[j], "geometry", bbox_tol, area_tol)

    for r in rows:
        entry = entries.get(r["name"])
        if entry is not None and not entry["reasons"]:
            result["matches"].append(entry)
    result["mismatches"] = sorted((e for e in entries.values() if e["reasons"]),
                                  key=lambda e: -e["severity"])
    return result


# ------------------------------------------------------------------------ the export's numbers


def export_stats(snapshot_dir) -> dict:
    """What one frozen split file says, from its own triangles: `tris`, `area` (sq in), `bbox`,
    `zero_area_tris` (triangles the print step collapsed to a line), `max_abs_coordinate` and
    `sig_digits`. The folder is a snapshot made by `engine.io.snapshot`."""
    objs = sorted(Path(snapshot_dir).glob("*.obj"))
    if len(objs) != 1:
        raise ValueError(f"{snapshot_dir}: expected exactly one .obj file, found {len(objs)}")
    mesh = read_obj(objs[0])
    if not mesh.n_faces:
        raise ValueError(f"{objs[0]}: no faces")
    tri = mesh.positions[mesh.face_v]
    length = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    points = tri.reshape(-1, 3)
    return {"tris": int(mesh.n_faces), "area": float(0.5 * length.sum()),
            "bbox": [points.min(axis=0).tolist(), points.max(axis=0).tolist()],
            "zero_area_tris": int((length == 0).sum()),
            "max_abs_coordinate": float(np.abs(points).max()), "sig_digits": int(mesh.sig_digits)}


# ----------------------------------------------------------------------- the verified copy


def _parts(path) -> list[str]:
    return [p.lower() for p in Path(path).resolve().parts]


def refuse_master(path) -> None:
    """The owner's campus model, `...\\02-SKETCHUP\\current\\...skp`, is never opened (AGENTS.md)."""
    parts = _parts(path)
    if any(a == "02-sketchup" and b == "current" for a, b in zip(parts, parts[1:])):
        raise ValueError(f"refusing to open the CHECKPOINT-17 master (under 02-SKETCHUP\\current): {path}")


def refuse_inside(path, folder) -> None:
    """Nothing is ever written inside the backup folder."""
    inside, outer = _parts(path), _parts(folder)
    if inside[:len(outer)] == outer:
        raise ValueError(f"refusing to write inside the backup folder {folder}: {path}")


def verified_copy(source: dict, backup_dir, dest_dir, name: str | None = None, *,
                  interval_s: float = 1.0, sleep=time.sleep) -> Path:
    """A copy of the backup `.skp` in `dest_dir`, whose sha256 is the one `source.json` froze --
    the only file of the backup the SDK is ever given. The backup is read once, through
    `engine.io.snapshot.copy_verified` (stable, copied, re-checked); a copy already in `dest_dir`
    with the right hash is reused, and one with the wrong hash is deleted first. A copy that does
    not match is deleted and `BackupMismatch` raised: it was never opened.

    `name` is the file's name in `source["backup"]`; by default the one `.skp` it lists."""
    backup = source["backup"]
    if name is None:
        skps = sorted(n for n in backup if n.lower().endswith(".skp"))
        if not skps:
            raise ValueError("source.json lists no .skp file of the backup")
        if len(skps) > 1:
            raise ValueError(f"source.json lists more than one .skp file of the backup {skps}: "
                             "say which one")
        name = skps[0]
    expected = backup[name]["sha256"]
    backup_dir, dest_dir = Path(backup_dir), Path(dest_dir)
    refuse_master(backup_dir)
    refuse_inside(dest_dir, backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    if dest.is_file():
        if sha256_file(dest) == expected:
            return dest
        dest.unlink()                                   # nothing unverified stays where it could be opened
    if not (backup_dir / name).is_file():
        raise FileNotFoundError(backup_dir / name)
    partial = dest_dir / f"{name}.partial"
    try:
        copy_verified(backup_dir / name, partial, interval_s, sleep)
        got = sha256_file(partial)
        if got != expected:
            raise BackupMismatch(
                f"{name}: the copy has sha256 {got}, but source.json froze {expected}: the backup "
                "changed after the freeze (run campus-freeze again). The copy was deleted and "
                "nothing was opened")
        os.replace(partial, dest)
    finally:
        partial.unlink(missing_ok=True)
    return dest


# ------------------------------------------------------------------------ the walk, in a child


def walk_argv() -> list[str]:
    """The command that reads a model and writes its walk: `engine.io.skp_reader`'s own."""
    return [sys.executable, "-m", "engine.io.skp_reader"]


def run_walk(skp, out_json, *, timeout_s: float = WALK_TIMEOUT_S, dll_path=None,
             min_free_commit_mb: float = MIN_FREE_COMMIT_MB, argv: list[str] | None = None) -> dict:
    """Walk the model `skp` in a child process that is killed after `timeout_s`, and return its
    walk (`out_json` is where the child writes it, and is kept). The SDK holds 2.5 GB for this
    model, so the child is not started with less than `min_free_commit_mb` of commit memory
    free (`NotEnoughMemory`); a child that fails, runs out of time or writes nothing raises
    `WalkFailed`. `argv` replaces the command (the tests' fake child); the model, `--out` and the
    output path are appended to it."""
    free = skp_reader.available_commit_mb()
    if free is not None and free < min_free_commit_mb:
        raise NotEnoughMemory(
            f"only {free:,.0f} MB of commit memory are free, and the walk of the backup is not started "
            f"with less than {min_free_commit_mb:,.0f} MB (it peaks at about 2.5 GB): close something "
            "or wait, then run it again")
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.unlink(missing_ok=True)                    # a file left by an earlier run is not this one's
    command = [*(walk_argv() if argv is None else argv), str(skp), "--out", str(out_json)]
    if dll_path is not None:
        command += ["--dll", str(dll_path)]
    repo = Path(__file__).resolve().parents[2]          # the checkout this module was imported from
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(repo), os.environ.get("PYTHONPATH")]))}
    try:
        done = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True,
                              errors="replace", timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        out_json.unlink(missing_ok=True)
        raise WalkFailed(f"the SketchUp walk timed out after {timeout_s:g} s and was killed") from exc
    if done.returncode != 0:
        tail = " ".join(done.stderr.split())[-600:]
        raise WalkFailed(f"the SketchUp walk failed with exit code {done.returncode}: {tail}")
    if not out_json.is_file():
        raise WalkFailed("the SketchUp walk finished but wrote no walk file")
    return json.loads(out_json.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------ the whole check


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _skipped(walk: dict, limit: int = 50) -> tuple[list[dict], int]:
    """The hidden and tag-off groups and instances the walk left out, with where each sat."""
    found: list[dict] = []

    def visit(node: dict, path: list[str]) -> None:
        for s in node["skipped"]:
            found.append({"path": " > ".join(path), "kind": s["kind"], "name": s["name"],
                          "reason": s["reason"]})
        for child in node["children"]:
            visit(child, path + [child["name"] or token(child)])

    visit(walk["root"], [])
    return found[:limit], len(found)


def _spread(values: list[float]) -> dict:
    v = sorted(values)
    return {"median": v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2,
            "min": v[0], "max": v[-1]}


def check_source(source_json, backup_dir, out_dir, *, name: str | None = None, summary=None,
                 bbox_tol: float | None = None, area_tol: float = AREA_TOL,
                 timeout_s: float = WALK_TIMEOUT_S, dll_path=None,
                 min_free_commit_mb: float = MIN_FREE_COMMIT_MB, walker=None,
                 interval_s: float = 1.0, sleep=time.sleep) -> dict:
    """The whole check: copy the backup `.skp` named in `source_json` into `<out_dir>/skp_copy/`
    (`verified_copy`: refused if its sha256 is not the frozen one), walk that copy in a child
    process (`<out_dir>/skp_walk.json`), compare every split file `source_json` froze with what the
    backup holds for it, and write `<out_dir>/skp_check.json` -- and `summary`, a short page, when
    given. Returns the report. Nothing is written beside the backup and the master is never opened.

    `bbox_tol` defaults to twice the export's print step, measured on its largest coordinate.
    `walker(skp, out_json) -> walk` replaces the child process (the tests' stand-in)."""
    source_json, backup_dir, out_dir = Path(source_json), Path(backup_dir), Path(out_dir)
    refuse_master(backup_dir)
    refuse_inside(out_dir, backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "skp_check.json").unlink(missing_ok=True)       # a failed run leaves no report that looks current
    source = json.loads(source_json.read_text(encoding="utf-8"))
    copy = verified_copy(source, backup_dir, out_dir / "skp_copy", name, interval_s=interval_s,
                         sleep=sleep)
    walk_json = out_dir / "skp_walk.json"
    if walker is None:
        walk = run_walk(copy, walk_json, timeout_s=timeout_s, dll_path=dll_path,
                        min_free_commit_mb=min_free_commit_mb)
    else:
        walk = walker(copy, walk_json)

    snapshots = {s["file"]: s["dir"] for s in source["snapshots"]}
    rows = []
    for m in source["manifest"]:
        stats = export_stats(snapshots[m["file"]])
        rows.append({"name": m["group"], "file": m["file"], **stats})
    max_abs = max(r["max_abs_coordinate"] for r in rows)
    step = print_step(max_abs, rows[0]["sig_digits"])
    tolerance = 2 * step if bbox_tol is None else bbox_tol
    units = sdk_units(walk)
    result = compare(rows, units, bbox_tol=tolerance, area_tol=area_tol)

    paired = result["matches"] + result["mismatches"]
    ambiguous_files = sum(len(a["rows"]) for a in result["ambiguities"] if not a["resolved"])
    skipped, skipped_total = _skipped(walk)
    report = {
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {"json": str(source_json), "created": source.get("created"),
                   "backup": copy.name, "backup_sha256": source["backup"][copy.name]["sha256"],
                   "copy": str(copy)},
        "tolerance": {"bbox_in": tolerance, "area_fraction": area_tol, "print_step_in": step,
                      "max_abs_coordinate": max_abs, "sig_digits": rows[0]["sig_digits"]},
        "sdk": {"api_version": walk.get("api_version"), "elapsed_s": walk.get("elapsed_s"),
                "peak_working_set_mb": walk.get("peak_working_set_mb"),
                "peak_commit_mb": walk.get("peak_commit_mb"), "totals": walk.get("totals"),
                "layers_bound": walk.get("layers_bound"), "units": len(units),
                "walk_json": str(walk_json)},
        "hidden": {**{k: walk["totals"][k] for k in ("hidden_nodes", "layer_hidden_nodes",
                                                     "hidden_faces", "layer_hidden_faces")},
                   "layers_bound": walk.get("layers_bound"), "skipped": skipped,
                   "skipped_total": skipped_total},
        "counts": {"files": len(rows), "matches": len(result["matches"]),
                   "mismatches": len(result["mismatches"]), "ambiguous_files": ambiguous_files,
                   "misses": len(result["misses"]), "sdk_only_units": len(result["sdk_only"]),
                   "paired_by_geometry": sum(1 for e in paired if e["paired_by"] == "geometry")},
        "measured": ({"paired": len(paired),
                      "bbox_max_dev": _spread([e["bbox_max_dev"] for e in paired]),
                      "area_rel": _spread([e["area_rel"] for e in paired]),
                      "area_more_in_backup": sum(1 for e in paired if e["area_rel"] > 0),
                      "tris_backup": sum(e["unit"]["tris"] for e in paired),
                      "tris_export": sum(e["export"]["tris"] for e in paired),
                      "tris_diff": sum(e["tris_diff"] for e in paired)}
                     if paired else {"paired": 0}),
        **result,
    }
    _write_atomic(out_dir / "skp_check.json", json.dumps(report, indent=1))
    if summary is not None:
        _write_atomic(Path(summary), render_markdown(report))
    return report


def render_markdown(report: dict) -> str:
    """A short page about `report`: what was compared, the counts, the five worst mismatches."""
    c, t, s, src = report["counts"], report["tolerance"], report["sdk"], report["source"]
    lines = [
        "# SDK cross-check: the CHECKPOINT-17 export against its backup", "",
        f"Run {report['created']}. Backup `{src['backup']}` (sha256 `{src['backup_sha256'][:12]}`, "
        f"read through a verified copy), export frozen in `source.json` of {src['created']} "
        f"({c['files']} files).",
        f"Tolerance: bounding box {_num(t['bbox_in'])} in (twice the export's print step of "
        f"{_num(t['print_step_in'])} in, measured on its largest coordinate {_num(t['max_abs_coordinate'])}), "
        f"area {t['area_fraction'] * 100:g} %.", "",
        "| result | files |", "|---|---:|",
        f"| match | {c['matches']} |", f"| mismatch | {c['mismatches']} |",
        f"| ambiguous | {c['ambiguous_files']} |", f"| miss | {c['misses']} |", "",
        "Ambiguous: several groups or files of one name that their shapes could not tell apart. "
        "Miss: no group of that name in the backup.", ""]
    extra = []
    if c["sdk_only_units"]:
        extra.append(f"{c['sdk_only_units']} groups of the backup hold faces that no file has")
    if c["paired_by_geometry"]:
        extra.append(f"{c['paired_by_geometry']} files were paired with their group by shape, because "
                     "the name does not say which is which")
    totals = s.get("totals") or {}
    hidden = report["hidden"]
    extra.append(
        f"the SketchUp walk saw {totals.get('groups', 0):,} groups, {totals.get('instances', 0):,} instances "
        f"and {totals.get('faces', 0):,} faces in {s.get('elapsed_s')} s (peak {s.get('peak_commit_mb')} MB "
        f"of commit); left out as hidden: {hidden['hidden_nodes']} groups or instances and "
        f"{hidden['hidden_faces']} faces, and as on a tag that is off: {hidden['layer_hidden_nodes']} "
        f"and {hidden['layer_hidden_faces']}" + ("" if hidden["layers_bound"] else
                                                 " (this DLL cannot tell tags: not applied)"))
    measured = report["measured"]
    if measured["paired"]:
        spread = measured["bbox_max_dev"]
        extra.append(
            f"bounding boxes of the {measured['paired']} paired files differ by at most "
            f"{_num(spread['max'])} in (median {_num(spread['median'])} in; the tolerance is "
            f"{_num(t['bbox_in'])} in)")
        diff = measured["tris_diff"]
        extra.append(
            f"triangles of the paired files (a face of v corners and h holes counts v + 2h - 2): the "
            f"backup {measured['tris_backup']:,}, the export {measured['tris_export']:,}; the export has "
            f"{abs(diff):,} triangles {'fewer' if diff >= 0 else 'more'} "
            f"({abs(diff) / max(measured['tris_backup'], 1) * 100:.1f} %)")
    lines += [f"- {e}" for e in extra] + [""]
    mismatches = report["mismatches"]
    if mismatches:
        more = report["measured"]["area_more_in_backup"]
        lines += [f"## Worst mismatches ({min(5, len(mismatches))} of {len(mismatches)})", "",
                  "| file | paired by | box, max off (in) | area: backup vs export | difference |",
                  "|---|---|---:|---|---:|"]
        for m in mismatches[:5]:
            lines.append(f"| {m['name']} | {m['paired_by']} | {_num(m['bbox_max_dev'])} | "
                         f"{m['unit']['area']:,.0f} vs {m['export']['area']:,.0f} sq in | "
                         f"{m['area_rel'] * 100:+.2f} % |")
        lines += ["", f"The reason for every mismatch, in words, is in `skp_check.json`. In {more} of the "
                  f"{report['measured']['paired']} paired files the backup has MORE area than the export.", ""]
    for amb in (a for a in report["ambiguities"] if not a["resolved"]):
        lines.append(f"- ambiguous `{amb['family']}` ({', '.join(amb['rows'])}): {amb['reason']}")
    for miss in report["misses"]:
        lines.append(f"- miss `{miss['name']}`: {miss['reason']}")
    for only in report["sdk_only"][:10]:
        lines.append(f"- SDK only `{only['key']}` ({only['path']}): {only['faces']} faces, "
                     f"{only['area']:,.0f} sq in")
    lines += ["", "Each export file holds the faces SketchUp's exporter gave it, and the owner's split "
              "rule decides which file that is (`engine/campus/skp_check.py`), so a file is compared "
              "with the faces that went into it, not with a whole group."]
    return "\n".join(lines) + "\n"
