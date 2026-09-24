from pathlib import Path

def sub(root, rel, old, new, count=1):
    p = Path(root) / rel
    s = p.read_text(encoding="utf-8")
    n = s.count(old)
    assert n == count, (root, rel, old[:60], n)
    p.write_text(s.replace(old, new), encoding="utf-8")
    print(f"{root}: {rel}: replaced {n}")

frag, cmp_, pipe = "engine/detectors/fragments.py", "engine/guard/compare.py", "engine/fixes/pipeline.py"
sub("mut_tj", frag, 'stats["n_joined_by_tjunction"] += sets.union(edge_face, f)', 'pass')
sub("mut_cop", frag, "for f, g in _coplanar_contacts(positions_w, face_w, contact_tol).tolist():", "for f, g in []:")
sub("mut_excuse", cmp_, "codes[own & may_show] = PX_FRAGMENT_REMOVED", "codes[own] = PX_FRAGMENT_REMOVED")
sub("mut_cap", cmp_, "if fragment.any() and int(fragment.sum()) > fragment_removed_cap * int((b.tri >= 0).sum()):", "if False:")
sub("mut_cap", cmp_, "if int(fragment.sum()) > fragment_removed_cap * int((b.tri >= 0).sum()):", "if False:")
sub("mut_grown", cmp_, "codes[~hit_before & hit_after] = PX_GROWN", "pass")
sub("mut_width", frag, "& (area <= max_area) & (width <= max_width)] = True", "& (area <= max_area)] = True")
sub("mut_bbox", pipe, """        "bbox_same": bool(np.array_equal(final_bbox[0], ref_bbox[0])
                          and np.array_equal(final_bbox[1], ref_bbox[1])),""",
    """        "bbox_same": bool(np.array_equal(final_mesh.positions.min(axis=0), mesh.positions.min(axis=0))
                          and np.array_equal(final_mesh.positions.max(axis=0), mesh.positions.max(axis=0))),""")
