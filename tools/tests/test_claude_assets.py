from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ["uc-repair-rules", "uc-handoff", "uc-run-unit"]
AGENTS = ["engine-builder", "unit-runner", "rules-reviewer", "hermes-reviewer", "census-analyst"]


def _front(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    head, body = text[4:].split("\n---\n", 1)
    meta = {}
    for line in head.splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, body


@pytest.mark.parametrize("name", SKILLS)
def test_skill_files(name):
    meta, body = _front(ROOT / ".claude" / "skills" / name / "SKILL.md")
    assert meta.get("name") == name and meta.get("description")
    assert "AGENTS.md" in body


@pytest.mark.parametrize("name", AGENTS)
def test_agent_files(name):
    meta, body = _front(ROOT / ".claude" / "agents" / f"{name}.md")
    assert meta.get("name") == name and meta.get("description") and meta.get("model")
    assert "AGENTS.md" in body
    assert "never dispatch" in body.lower()
