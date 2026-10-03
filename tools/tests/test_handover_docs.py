from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "docs" / "superpowers" / "records"


def test_hermes_md_is_the_queue_entry_point():
    text = (ROOT / "HERMES.md").read_text(encoding="utf-8")
    for phrase in ("Read HERMES.md and do the next job", "tools/jobs.py next --for hermes",
                   "jobs.py done", "AGENTS.md", "hermes/<id>-report.md", "Hermes-Job:"):
        assert phrase in text, phrase


def test_brief_template_has_items_and_acceptance_commands():
    text = (RECORDS / "briefs" / "TEMPLATE.md").read_text(encoding="utf-8")
    for heading in ("## Goal", "## Files", "## Items", "## Acceptance commands", "## Report"):
        assert heading in text, heading


def test_report_format_asks_for_real_output():
    text = (RECORDS / "hermes" / "README.md").read_text(encoding="utf-8")
    assert "## Acceptance command outputs" in text
    assert "real output" in text
