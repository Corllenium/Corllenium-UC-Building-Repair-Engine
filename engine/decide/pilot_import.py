"""Load the already-paid Jev pilot answers (`data/campus/jev_pilot.json`) into the VPS decide service as pending
suggestions, so the owner can review them and later live asks hit the cache instead of paying Jev again.

The service keys its cache on the exact question (state, kind, instructions, criteria). So the questions are
rebuilt here with the real classifiers, not by hand: a capturing decider is passed to `classify_group_names` and
`classify_materials`, records what they ask and answers nothing. Each captured question is paired with the
pilot's answer by the index in its id (`"<i>:<field>"`).

- Groups: `pilot.group_rows(source)` gives the rows (it reads the frozen OBJ snapshots `source.json` names).
  Four questions per group: building, type, floor, duplicate.
- Materials: only the pilot's spot-check names, and only `mat.category` (the pilot kept no confidence for `trim`).
- A decision is imported only when its source is "jev" and its answer is not None, and the answer is one of the
  question's own options (the service refuses anything else).
- Only text leaves the machine, as in a live ask. The password is `UC_DECIDE_PASSWORD` and is handled by
  `RemoteDecider` (environment first, else the one `.env` line; never printed or logged).
"""
from __future__ import annotations

from pathlib import Path

from engine.decide import jev, wire
from engine.decide.jev import classify_group_names, classify_materials
from engine.decide.pilot import group_rows
from engine.decide.remote import PASSWORD_VAR, RemoteDecider

IMPORT_PATH = "/api/decide/import"
#: Items per POST.
CHUNK = 200
#: The import is a one-off write of up to a few hundred rows; allow more than an ask's 10 s.
IMPORT_TIMEOUT = 60.0
_GROUP_FIELDS = ("building", "type", "floor", "duplicate")


class _Capture:
    """A decider that records every `(state, questions)` it is asked and answers none."""

    def __init__(self):
        self.state: dict | None = None
        self.questions: dict = {}

    def ask(self, state, questions):
        self.state = {"text": state} if isinstance(state, str) else state
        self.questions.update(questions)
        return {qid: jev._none() for qid in questions}


def _pilot_model(pilot: dict) -> str:
    models = (pilot.get("calls") or {}).get("models") or []
    if len(models) == 1 and isinstance(models[0], str) and models[0]:
        return models[0]
    return str(pilot.get("model") or jev.MODEL)


def _usable(decision) -> bool:
    return isinstance(decision, dict) and decision.get("source") == "jev" and decision.get("answer") is not None


def _group_answer(field: str, answer):
    """The pilot stores the building as the campus-map key and the floor as an int; the questions' options are
    the labels ("MAIN INFRASTRUCTURE") and the keys ("5")."""
    if field == "building":
        return jev._LABEL_OF.get(answer, answer)
    if field == "floor":
        try:
            return str(int(answer))
        except (TypeError, ValueError):
            return None
    return answer


def _item(state: dict, question, answer, confidence, model: str) -> dict | None:
    if isinstance(question, jev.NoulQ):
        if not isinstance(answer, bool):          # 1 == True in Python, but the service wants the JSON bool
            return None
    elif not isinstance(answer, str) or answer not in wire.options_of(question):
        return None
    return {"state": state, "question": wire.question_to_json(question), "answer": answer,
            "confidence": float(confidence or 0.0), "probabilities": {}, "model": model}


def build_import_items(source: dict, materials: dict, pilot: dict) -> list[dict]:
    """The items of `build_import_report`, without the unreproducible names."""
    return build_import_report(source, materials, pilot)[0]


def build_import_report(source: dict, materials: dict, pilot: dict) -> tuple[list[dict], list[str]]:
    """`(items, unreproducible)`. An item is `{state, question, answer, confidence, probabilities, model}` per
    pilot answer that can be imported. `materials` is the content of `materials.json` (or its inner
    `{name: {...}}` dict). A group whose rebuilt row cannot reproduce the paid question is skipped, never
    imported under a wrong key, and its name is listed in `unreproducible`: its rebuilt `footprint_building`
    differs from the pilot row's, or its z range is None (the snapshot OBJ is missing)."""
    model = _pilot_model(pilot)
    items: list[dict] = []
    unreproducible: list[str] = []

    # ---- groups
    rows = group_rows(source)
    cap = _Capture()
    classify_group_names(rows, cap)
    pilot_rows = {r["name"]: r for r in (pilot.get("groups") or {}).get("rows", [])}
    for i, row in enumerate(rows):
        prow = pilot_rows.get(row["name"])
        if prow is None:
            continue
        if (row["z_min"] is None or row["z_max"] is None
                or row["footprint_building"] != prow.get("footprint_building")):
            unreproducible.append(row["name"])
            continue
        for field in _GROUP_FIELDS:
            decision = prow.get(field)
            if not _usable(decision):
                continue
            item = _item(cap.state, cap.questions[f"{i}:{field}"], _group_answer(field, decision["answer"]),
                         decision.get("confidence"), model)
            if item is not None:
                items.append(item)

    # ---- materials: the spot-check names, the category only
    known = materials.get("materials", materials) if isinstance(materials, dict) else {}
    spot = (pilot.get("materials") or {}).get("spot_check", [])
    infos = []
    for s in spot:
        m = known.get(s["name"]) if isinstance(known, dict) else None
        if isinstance(m, dict):
            info = {"name": s["name"], "texture": Path(m["map_kd"]).name if m.get("map_kd") else None,
                    "kd": m.get("kd")}
        else:
            info = {"name": s["name"], "texture": s.get("texture"), "kd": s.get("kd")}
        infos.append(info)
    cap = _Capture()
    classify_materials(infos, cap)
    for i, s in enumerate(spot):
        decision = {"answer": s.get("category"), "confidence": s.get("confidence"), "source": "jev"}
        if not _usable(decision):
            continue
        item = _item(cap.state, cap.questions[f"{i}:category"], decision["answer"], decision["confidence"], model)
        if item is not None:
            items.append(item)
    return items, unreproducible


def counts(items: list[dict], unreproducible: list[str] | None = None) -> dict:
    """Items and distinct subjects per kind, and the number of unreproducible groups."""
    groups = [it for it in items if it["question"]["qtype"].startswith("inv.")]
    mats = [it for it in items if it["question"]["qtype"].startswith("mat.")]
    return {"groups": len(groups), "group_rows": len({it["question"]["subject"] for it in groups}),
            "materials": len(mats), "material_names": len({it["question"]["subject"] for it in mats}),
            "unreproducible": len(unreproducible or [])}


def import_items(items: list[dict], url: str, *, user: str | None = None, password: str | None = None,
                 timeout: float = IMPORT_TIMEOUT, env_file: Path | str | None = None) -> dict:
    """POST the items in chunks of `CHUNK`. Returns the summed `{"added", "skipped", "invalid"}`. Raises
    `ValueError` for a bad URL and `RuntimeError` (class name or HTTP status only) for a failed chunk, which
    ends the run; chunks already sent stay sent (the service skips what it already holds)."""
    kw = {} if user is None else {"user": user}
    client = RemoteDecider(url, password=password, timeout=timeout, env_file=env_file, **kw)
    if not client.available:
        raise RuntimeError(f"no {PASSWORD_VAR} (environment or env file)")
    total = {"added": 0, "skipped": 0, "invalid": 0}
    for start in range(0, len(items), CHUNK):
        chunk = items[start:start + CHUNK]
        reply, error = client._call("POST", IMPORT_PATH, {"items": chunk}, len(chunk))
        if error:
            raise RuntimeError(f"import failed at item {start}: {error}")
        if not isinstance(reply, dict) or not all(isinstance(reply.get(k), int) and not isinstance(reply.get(k), bool)
                                                  for k in total):
            raise RuntimeError(f"import failed at item {start}: BadReply")
        for k in total:
            total[k] += reply[k]
    return total
