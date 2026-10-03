from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUST = [
    "Weld above 0.1 mm", "select_interior_faces", "Fill Holes", "Make Manifold", "Decimate",
    "whole-campus jobs", "every facade texture is still there", "the problems are solved",
    "nothing visible to the eye was deleted or covered", "eye height", "_Cull = 0",
    "Only `engine/fixes/solidify.py` may invent vertices", "tools/jobs.py",
]


def test_agents_md_holds_every_binding_rule():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    missing = [m for m in MUST if m not in text]
    assert not missing, missing


def test_claude_md_imports_agents_md():
    assert "@AGENTS.md" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_handoff_rules_point_to_agents_md():
    text = (ROOT / "docs/superpowers/records/HANDOFF.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in text
