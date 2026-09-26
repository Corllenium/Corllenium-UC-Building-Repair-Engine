"""Every image errors.json names exists, and every owner screenshot is used somewhere.

Spec: docs/superpowers/specs/2026-09-26-errors-and-fixes-page-design.md ("every image the owner
sent appears somewhere"). Exit code 1 when anything is missing or unused.
"""
import argparse
import json
import sys
from pathlib import Path


def _named_images(errors_json: Path) -> set[str]:
    doc = json.loads(Path(errors_json).read_text(encoding="utf-8"))
    items = [i for e in doc.get("errors", []) for i in e.get("you_saw", []) + e.get("after", [])]
    items += doc.get("other_screenshots", [])
    return {i["image"] for i in items if i.get("image")}


def missing_images(errors_json, img_dir) -> list[str]:
    return sorted(n for n in _named_images(errors_json) if not (Path(img_dir) / n).is_file())


def unused_owner_images(errors_json, owner_images_json) -> list[str]:
    owner = json.loads(Path(owner_images_json).read_text(encoding="utf-8"))
    used = _named_images(errors_json)
    return sorted(r["file"] for r in owner if r["file"] not in used)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the Errors & fixes page's images.")
    ap.add_argument("--errors-json", type=Path, default=Path("web/public/docs/errors.json"))
    ap.add_argument("--doc-dir", type=Path, default=Path("data/errors_doc"))
    a = ap.parse_args(argv)
    missing = missing_images(a.errors_json, a.doc_dir / "img")
    unused = unused_owner_images(a.errors_json, a.doc_dir / "owner_images.json")
    for n in missing:
        print(f"missing: {n}")
    for n in unused:
        print(f"unused owner screenshot: {n}")
    print(f"{len(missing)} missing, {len(unused)} unused")
    return 1 if missing or unused else 0


if __name__ == "__main__":
    sys.exit(main())
