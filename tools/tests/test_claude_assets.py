from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ["uc-repair-rules", "uc-handoff", "uc-run-unit", "uc-prompt-audit", "uc-validate-floor"]
AGENTS = ["engine-builder", "unit-runner", "rules-reviewer", "hermes-reviewer", "census-analyst",
          "prompt-auditor", "floor-validator"]


def _front(path: Path) -> tuple[dict, str]:
    """Parse the frontmatter as real YAML, the way Claude Code does. An unquoted ': ' inside a value
    makes it invalid, and then the skill's description silently never loads (prompt audit F1)."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    head, body = text[4:].split("\n---\n", 1)
    meta = yaml.safe_load(head)
    assert isinstance(meta, dict), f"{path}: frontmatter is not a YAML mapping"
    return {k: str(v) for k, v in meta.items()}, body


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
