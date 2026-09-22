import pytest
from sqlalchemy import select
from api.models import Model, ModelVersion, VersionAsset, IssueType, FixRun


def test_seeded_issue_types(db):
    stmt = select(IssueType)
    issue_types = list(db.scalars(stmt))
    keys = {it.key for it in issue_types}
    assert "degenerate" in keys
    assert "excess_subdivision" in keys
    assert "oriented_visibility" in keys
    assert "coplanar_overlap" in keys
    assert "double_sided_pair" in keys


def test_create_model_and_versions(db):
    model = Model(name="test_sidewalk", source_file="test_sidewalk.obj")
    db.add(model)
    db.commit()
    db.refresh(model)

    assert model.id is not None
    assert model.name == "test_sidewalk"

    version = ModelVersion(
        model_id=model.id,
        kind="snapshot",
        sha256="abcdef1234567890",
        tri_count=1200,
        coord_quantum=[0.01, 0.1, 0.01],
        origin_offset=[100.0, 200.0, 0.0],
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    assert version.id is not None
    assert version.kind == "snapshot"
    assert len(model.versions) == 1
    assert model.versions[0].tri_count == 1200

    asset = VersionAsset(
        version_id=version.id,
        kind="obj",
        name="test_sidewalk.obj",
        path="snapshots/abc/test_sidewalk.obj",
        sha256="abcdef1234567890",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    assert asset.id is not None
    assert len(version.assets) == 1

    fix_run = FixRun(
        version_id=version.id,
        status="completed",
        config={"n_dirs": 128},
        report_json={"tris_before": 1200, "tris_after": 800},
    )
    db.add(fix_run)
    db.commit()
    db.refresh(fix_run)

    assert fix_run.id is not None
    assert fix_run.status == "completed"
    assert fix_run.report_json is not None
    assert fix_run.report_json["tris_after"] == 800
