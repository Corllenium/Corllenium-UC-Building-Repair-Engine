"""Copy the two test objects out of the LIVE export folder, with stability + manifest checks."""
import hashlib
import os
import re
import shutil
import sys
import time

from _common import FILES, SNAP, SOURCE, load_obj, save


def stat_key(path):
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns


def stable(path, wait=2.0):
    if not path.exists():
        sys.exit(f"source rebuilding: {path.name} missing")
    a = stat_key(path)
    time.sleep(wait)
    if not path.exists() or stat_key(path) != a or a[0] == 0:
        sys.exit(f"source rebuilding: {path.name} changed during read")
    return a


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest():
    rows = {}
    lines = (SOURCE / "split" / "_MANIFEST.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[1:]:
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 2:
            rows[parts[0]] = int(parts[1].replace(",", ""))
    return rows


SNAP.mkdir(parents=True, exist_ok=True)
man = manifest()
report, used = {}, set()
for name in FILES:
    src = SOURCE / "split" / name
    key = stable(src)
    dst = SNAP / name
    shutil.copyfile(src, dst)
    if stat_key(src) != key:
        sys.exit(f"source rebuilding: {name} changed during copy")
    m = load_obj(dst)
    used.update(m["mats"])
    report[name] = {
        "sha256": sha256(dst),
        "bytes": key[0],
        "tris": int(len(m["fv"])),
        "manifest_tris": man.get(name),
        "tris_match_manifest": man.get(name) == len(m["fv"]),
    }

mtl_src = SOURCE / "CKPT17-CLEAN.mtl"
stable(mtl_src, wait=1.0)
shutil.copyfile(mtl_src, SNAP / "CKPT17-CLEAN.mtl")
textures, missing, cur = [], [], None
for line in (SNAP / "CKPT17-CLEAN.mtl").read_text(encoding="utf-8", errors="replace").splitlines():
    line = line.strip()
    if line.startswith("newmtl "):
        cur = line[7:].strip()
    elif line.startswith("map_Kd ") and cur in used:
        rel = line[7:].strip()
        if (SOURCE / rel).exists():
            (SNAP / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / rel, SNAP / rel)
            textures.append(rel)
        else:
            missing.append(rel)

report["materials_used"] = sorted(used)
report["textures_copied"] = textures
report["textures_missing"] = missing
save("snapshot", report)
for k, v in report.items():
    print(k, "=>", v)
