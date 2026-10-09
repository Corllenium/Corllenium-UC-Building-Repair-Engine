"""Job P2-E8c item 3: the SketchUp helper `tools/sketchup/needs_modelling_views.rb` is read-only.

It moves the camera to each spot of `needs_modelling.json` and draws a temporary outline. It must never save the
model or add geometry, scenes or layers. SketchUp is not run here (a smoke run happens only if the controller asks),
so this test reads the script: comments and string contents are removed (an interpolation inside a string stays,
it is code), and what is left may contain none of the calls that change or save a model, and may touch the model
only through the three calls the viewer needs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "sketchup" / "needs_modelling_views.rb"

#: The brief's list, as patterns on the code: `save`, `add_face`, `add_line`, `entities.add`, `pages.add`, `layers.add`.
FORBIDDEN = {
    "save": r"\bsave\w*",
    "add_face": r"\badd_face\w*",
    "add_line": r"\badd_line\w*",
    "entities.add": r"\bentities\b\s*\.\s*add\w*",
    "pages.add": r"\bpages\b\s*\.\s*add\w*",
    "layers.add": r"\b(layers|tags)\b\s*\.\s*add\w*",
    # anything else that adds to a model, or changes one
    "any .add": r"\.\s*add\b",
    "add_ other than the menu's and the dialog's": r"\badd_(?!item\b|submenu\b|action_callback\b)\w+",
    "operations": r"\b(start|commit|abort)_operation\b",
    "entities, definitions, selection, pages, layers, materials": r"\.\s*(entities|definitions|selection|pages|layers|tags|materials|styles|attribute_dictionaries)\b",
    "changes to an entity": r"(\.erase!|\.transform!|\.transformation\s*=|\.material\s*=|\.hidden\s*=|\.visible\s*=|\.layer\s*=|"
                            r"\.name\s*=|set_attribute|delete_attribute|\.explode|\.make_unique|\.move!|\.pushpull|\.followme)",
    "writing or running": r"(File\s*\.\s*(write|open|new|delete|rename|binwrite|chmod)|\bIO\b|FileUtils|write_image|\.export|"
                          r"open_file|send_action|\bsystem\b|\bexec\b|\beval\b|%x|`)",
}
#: The only methods of the model the helper calls.
MODEL_CALLS = {"active_view", "bounds", "select_tool"}


def code_only(text: str) -> str:
    """The Ruby `text` without comments and without the contents of string literals ('...' and "..."); the code
    inside a `#{...}` of a double-quoted string is kept. Heredocs, `%q` strings and regexp literals are not handled
    (`test_the_script_uses_no_literal_the_scanner_cannot_read` refuses them)."""
    def scan(i: int, closing: str | None) -> tuple[str, int]:
        out, depth = [], 0
        while i < len(text):
            c = text[i]
            if closing == "}" and c == "}" and depth == 0:
                return "".join(out), i + 1
            if closing == "}":
                depth += (c == "{") - (c == "}")
            if c == "#":                                           # a comment, to the end of the line
                while i < len(text) and text[i] != "\n":
                    i += 1
                continue
            if c in "'\"":
                i = string(i, c, out)
                continue
            out.append(c)
            i += 1
        return "".join(out), i

    def string(i: int, quote: str, out: list) -> int:
        out.append(quote)
        i += 1
        while i < len(text) and text[i] != quote:
            if text[i] == "\\":
                i += 2
                continue
            if quote == '"' and text[i:i + 2] == "#{":
                inner, i = scan(i + 2, "}")
                out.append(" " + inner + " ")
                continue
            i += 1
        out.append(quote)
        return i + 1

    return scan(0, None)[0]


def _code() -> str:
    return code_only(SCRIPT.read_text(encoding="utf-8"))


def test_the_script_exists_and_is_for_the_owners_own_working_copy():
    text = SCRIPT.read_text(encoding="utf-8")
    head = text.split("require", 1)[0]
    assert "NEVER RUN THIS ON THE CHECKPOINT-17 MASTER" in head
    assert "working copy" in head.lower() and "never saves the model" in head
    assert re.search(r"^\s*JSON_PATH = ", text, re.M), "the needs_modelling.json path is set at the top"


@pytest.mark.parametrize("name", sorted(FORBIDDEN))
def test_the_script_calls_nothing_that_saves_or_changes_a_model(name):
    hits = [m.group(0) for m in re.finditer(FORBIDDEN[name], _code())]
    assert hits == [], f"{SCRIPT.name} contains {name}: {hits}"


def test_the_script_touches_the_model_only_through_the_viewers_three_calls():
    model_calls = set(re.findall(r"\bmodel\s*\.\s*(\w+)", _code()))
    assert model_calls <= MODEL_CALLS, f"unexpected model calls: {sorted(model_calls - MODEL_CALLS)}"
    active = set(re.findall(r"\bactive_model\s*\.\s*(\w+)", _code()))
    assert active <= MODEL_CALLS, f"unexpected model calls: {sorted(active - MODEL_CALLS)}"


def test_the_script_uses_no_literal_the_scanner_cannot_read():
    assert not re.search(r"<<[~-]?['\"A-Z_]|%[qQwWiIrx]?[({\[<|!/]|(?<![\w)\]])/[^/\s*]", _code()), \
        "heredocs, %-literals and regexp literals hide code from the scan: do not use them"


def test_the_menu_and_the_camera_are_as_the_brief_says():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "UI.menu('Extensions').add_submenu(MENU_TITLE)" in text and "MENU_TITLE = 'UC Needs Modelling'" in text
    for label in ("Next spot", "Previous spot", "List", "Done"):
        assert f"add_item('{label}')" in text
    assert "view.camera = Sketchup::Camera.new(" in text and "model.active_view.camera = cam" in text
    assert "restore_camera" in text and "def self.done" in text
    assert "view.draw(GL_LINE_LOOP" in text, "the outline is drawn in the view, not added to the model"
    assert "'suggested_view'" in text and "'border'" in text and "schema_version" in text


def test_ruby_blocks_are_balanced():
    """A crude syntax check without a Ruby: every `def`, `class`, `module`, `if`/`unless`/`while` at the start of a
    statement, and `do` block opens an `end`. SketchUp is where it really runs."""
    code = _code()
    opens = 0
    for line in code.splitlines():
        s = line.strip()
        if re.match(r"(def|class|module|if|unless|while|until|case|begin)\b", s):
            opens += 1
        elif re.search(r"\bdo(\s*\|[^|]*\|)?\s*$", s):
            opens += 1
        elif re.search(r"=\s*(if|unless|case)\b", s):
            opens += 1
        opens -= len(re.findall(r"(?<![\w.])end\b", s))
    assert opens == 0, f"{opens} unclosed blocks"


# ------------------------------------------------------------------------ the scanner itself catches what it should

@pytest.mark.parametrize("line, name", [
    ("Sketchup.active_model.save('x.skp')", "save"),
    ("model.save_copy(path)", "save"),
    ("ents.add_face(a, b, c)", "add_face"),
    ("ents.add_line(a, b)", "add_line"),
    ("model.entities.add_group", "entities.add"),
    ("model.pages.add('scene')", "pages.add"),
    ("model.layers.add('x')", "layers.add"),
    ("model.start_operation('x', true)", "operations"),
    ("x = \"#{model.entities.add_face(a, b, c)}\"", "add_face"),      # an interpolation is code
    ("File.write('x', 'y')", "writing or running"),
])
def test_the_scan_catches_each_forbidden_call(line, name):
    assert re.search(FORBIDDEN[name], code_only(line)), f"{name} not found in {line!r}"


def test_the_scan_ignores_comments_and_strings():
    sample = "# this never saves; entities.add_face\nputs 'save and add_face'\nputs \"save #{1 + 1}\" # entities.add\nx = 1"
    cleaned = code_only(sample)
    assert "save" not in cleaned and "add_face" not in cleaned and "entities.add" not in cleaned
    assert "1 + 1" in cleaned and "x = 1" in cleaned
