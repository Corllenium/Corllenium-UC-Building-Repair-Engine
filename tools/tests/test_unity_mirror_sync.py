from pathlib import Path

from tools.unity_mirror import check, sync


def _setup(tmp_path):
    owner = tmp_path / "owner" / "CampusModelImporter.cs"
    owner.parent.mkdir()
    owner.write_text("public class CampusModelImporter {}\n")
    mirror = tmp_path / "mirror"
    (mirror / "Assets" / "Editor").mkdir(parents=True)
    return mirror, owner


def test_sync_copies_the_importer_and_check_passes(tmp_path):
    mirror, owner = _setup(tmp_path)
    sha = sync(mirror, owner)
    assert (mirror / "Assets" / "Editor" / "CampusModelImporter.cs").read_text() == owner.read_text()
    assert check(mirror, owner) == (True, sha, sha)


def test_check_fails_after_the_owner_changes_the_importer_naming_both_hashes(tmp_path):
    mirror, owner = _setup(tmp_path)
    old = sync(mirror, owner)
    owner.write_text("public class CampusModelImporter { int x; }\n")
    ok, have, want = check(mirror, owner)
    assert not ok and have == old and want != old


def test_sync_never_writes_to_the_owner_file(tmp_path):
    mirror, owner = _setup(tmp_path)
    before = owner.stat().st_mtime_ns
    sync(mirror, owner)
    assert owner.stat().st_mtime_ns == before


def test_a_utf8_bom_does_not_change_the_hash(tmp_path):
    # Unity may add or strip a BOM when it touches a script; the text is what counts.
    mirror, owner = _setup(tmp_path)
    text = "public class CampusModelImporter { /* café */ }\n"
    owner.write_bytes(text.encode("utf-8"))
    sync(mirror, owner)
    (mirror / "Assets" / "Editor" / "CampusModelImporter.cs").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    ok, have, want = check(mirror, owner)
    assert ok and have == want
