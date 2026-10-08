"""A suggest-only, confidence-gated wrapper around TypeSafe's Jev model (`typesafe-sdk`, model `jev-latest`).

Jev takes text plus typed questions (a yes/no `Noul`, a `Choice` among labels, an ordinal `Score`) and
answers each with a confidence. This module turns those answers into `Decision`s. A decision is
`accepted` only when its confidence reaches the decider's `min_confidence`; an uncertain one goes to the
owner or the deterministic path. It is a soft helper:

- It is never used to delete or keep geometry, to set a guard tolerance, or to give a Validator verdict
  (AGENTS.md sections 3 and 6).
- Only text leaves the machine: group names, material names, texture file names, small numbers. Never
  meshes, textures or pixels.
- No key or no SDK means `source = "none"`, `accepted = False`, no network and no waiting.

The key (`TYPESAFE_API_KEY`) comes from the process environment first; if it is not set, the git-ignored
repo-root `.env` is read and ONLY its `TYPESAFE_API_KEY=` line is taken. It is passed to the client
explicitly and never put into `os.environ`. It is never printed, logged, `repr`ed, or put into an
exception message or a `Decision`: a failed call records only the exception's class name and HTTP status.

Questions are written with the neutral `NoulQ` / `ChoiceQ` / `ScoreQ`; `_make_sdk_client` adapts them to
the SDK's `Noul` / `Choice` / `Score`, so this module and its tests work without the SDK installed.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger(__name__)

MODEL = "jev-latest"
ENV_VAR = "TYPESAFE_API_KEY"


# ------------------------------------------------------------------------------------- questions


@dataclass(frozen=True)
class NoulQ:
    """A yes/no question. Its instructions must be self-contained: ids are not sent to the model."""
    instructions: str


@dataclass(frozen=True)
class ChoiceQ:
    """A pick among labels: `criteria` maps each label to an optional description."""
    instructions: str
    criteria: Mapping[str, str | None]


@dataclass(frozen=True)
class ScoreQ:
    """An ordinal score: `criteria[i]` describes level `i`."""
    instructions: str
    criteria: list[str]


# ------------------------------------------------------------------------------------- decisions


@dataclass
class Decision:
    answer: str | float | bool | None
    confidence: float
    probabilities: dict
    source: str            # "jev" | "none" (no key / no SDK) | "error"
    accepted: bool         # confidence >= the decider's min_confidence
    error: str = ""        # on "error": the exception class name and HTTP status only, never its message


def _none() -> Decision:
    return Decision(None, 0.0, {}, "none", False)


def _failed(error: str) -> Decision:
    return Decision(None, 0.0, {}, "error", False, error)


# ------------------------------------------------------------------------------------- the key


def _repo_root_env() -> Path:
    """`.env` in the directory that holds this engine's `pyproject.toml` (the repo or worktree root)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent / ".env"
    return here.parents[2] / ".env"


#: Tests point this at a file that does not exist; nothing else should change it.
DEFAULT_ENV_FILE: Path = _repo_root_env()

_KEY_LINE = re.compile(r"^\s*(?:export\s+)?" + ENV_VAR + r"\s*=\s*(.*?)\s*$")


def read_env_key(path: Path) -> str | None:
    """The `TYPESAFE_API_KEY=` value in `path`, or None. Every other line is skipped unread. With several
    key lines the last one wins, as dotenv does (an empty last one means no key)."""
    found: str | None = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                m = _KEY_LINE.match(line)
                if not m:
                    continue
                value = m.group(1)
                if value[:1] in ("'", '"'):
                    end = value.find(value[0], 1)
                    value = value[1:end] if end > 0 else value[1:]
                else:
                    value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
                found = value.strip() or None
    except OSError:
        return None
    return found


def sdk_importable() -> bool:
    try:
        import typesafe_sdk  # noqa: F401
    except Exception:
        return False
    return True


class _SdkAdapter:
    """Wraps `typesafe_sdk.TypeSafeClient`: turns the neutral questions into the SDK's own."""

    def __init__(self, client):
        self._client = client

    def system_one(self, state, questions):
        import typesafe_sdk as sdk
        sdk_questions: dict[str, Any] = {}
        for qid, q in questions.items():
            if isinstance(q, NoulQ):
                sdk_questions[qid] = sdk.Noul(instructions=q.instructions)
            elif isinstance(q, ChoiceQ):
                sdk_questions[qid] = sdk.Choice(instructions=q.instructions, criteria=dict(q.criteria))
            elif isinstance(q, ScoreQ):
                sdk_questions[qid] = sdk.Score(instructions=q.instructions, criteria=list(q.criteria))
            else:
                raise TypeError(f"unsupported question type {type(q).__name__}")
        return self._client.system_one(state=state, questions=sdk_questions)


def _make_sdk_client(key: str, model: str):
    import typesafe_sdk as sdk
    return _SdkAdapter(sdk.TypeSafeClient(api_key=key, model=model))


def _error_text(exc: BaseException) -> str:
    """Class name and HTTP status only: an SDK message could carry a request line with credentials."""
    status = getattr(exc, "status", None)
    return type(exc).__name__ + (f" status={status}" if isinstance(status, int) else "")


# ------------------------------------------------------------------------------------- the decider


class JevDecider:
    """Asks Jev typed questions and gates the answers by confidence."""

    def __init__(self, client=None, min_confidence: float = 0.8, batch: int = 20, *,
                 env_file: Path | str | None = None, model: str = MODEL):
        if batch < 1:
            raise ValueError("batch must be at least 1")
        self.min_confidence = float(min_confidence)
        self.batch = int(batch)
        self.model = model
        #: One entry per call: questions, latency_s, input_tokens, output_tokens, model, ok.
        self.calls: list[dict] = []
        self._client = client
        self._client_error: str | None = None     # set once if the client cannot be made; never retried
        self._injected = client is not None
        self._key: str | None = None
        self._env_file = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
        if not self._injected and sdk_importable():
            self._key = os.environ.get(ENV_VAR) or read_env_key(self._env_file)
            self._key = self._key or None

    def __repr__(self) -> str:
        return (f"JevDecider(available={self.available}, min_confidence={self.min_confidence}, "
                f"batch={self.batch}, model={self.model!r})")

    @property
    def available(self) -> bool:
        """The SDK imports and a key is set, or a client was injected."""
        return self._injected or self._key is not None

    # ---------------------------------------------------------------------------------- ask

    def ask(self, state: str | dict, questions: dict) -> dict[str, Decision]:
        if not self.available:
            return {qid: _none() for qid in questions}
        state_dict = {"text": state} if isinstance(state, str) else state
        out: dict[str, Decision] = {}
        ids = list(questions)
        for start in range(0, len(ids), self.batch):
            chunk = {qid: questions[qid] for qid in ids[start:start + self.batch]}
            if self._client_error is not None:
                out.update({qid: _failed(self._client_error) for qid in chunk})
                continue
            out.update(self._call(state_dict, chunk))
        return out

    def _get_client(self):
        """The client, made on first use. If making it fails, the failure is remembered (class name and
        status only) so later batches fail at once instead of trying again."""
        if self._client is None:
            try:
                self._client = _make_sdk_client(self._key, self.model)
            except Exception as exc:  # noqa: BLE001
                self._client_error = _error_text(exc)
                raise
        return self._client

    def _call(self, state: dict, chunk: dict) -> dict[str, Decision]:
        t0 = time.perf_counter()
        entry = {"questions": len(chunk), "latency_s": 0.0, "input_tokens": None, "output_tokens": None,
                 "model": None, "ok": False}
        try:
            response = self._get_client().system_one(state=state, questions=chunk)
        except Exception as exc:  # noqa: BLE001 -- any SDK failure fails this batch only
            entry["latency_s"] = round(time.perf_counter() - t0, 4)
            entry["error"] = _error_text(exc)
            self.calls.append(entry)
            log.warning("jev call failed: %d questions, %s, %.2fs", len(chunk), entry["error"], entry["latency_s"])
            return {qid: _failed(entry["error"]) for qid in chunk}
        entry["latency_s"] = round(time.perf_counter() - t0, 4)
        usage = getattr(response, "usage", None)
        entry["input_tokens"] = getattr(usage, "input_tokens", None)
        entry["output_tokens"] = getattr(usage, "output_tokens", None)
        entry["model"] = getattr(response, "model", None)
        entry["ok"] = True
        self.calls.append(entry)
        answers = getattr(response, "answers", None) or {}
        result: dict[str, Decision] = {}
        for qid, spec in chunk.items():
            try:
                result[qid] = self._decision(spec, answers[qid])
            except Exception as exc:  # noqa: BLE001 -- a missing or malformed answer
                result[qid] = _failed("MissingAnswer" if isinstance(exc, KeyError) else _error_text(exc))
            d = result[qid]
            log.debug("jev %s source=%s confidence=%.3f accepted=%s latency=%.2fs tokens=%s/%s",
                      str(qid)[:200], d.source, d.confidence, d.accepted, entry["latency_s"],
                      entry["input_tokens"], entry["output_tokens"])
        return result

    def _decision(self, spec, answer) -> Decision:
        if isinstance(spec, NoulQ):
            p = float(answer.noul)
            confidence = max(p, 1.0 - p)
            return Decision(p >= 0.5, confidence, {"yes": p, "no": 1.0 - p}, "jev", confidence >= self.min_confidence)
        confidence = float(answer.confidence)
        value = answer.choice if isinstance(spec, ChoiceQ) else float(answer.score)
        return Decision(value, confidence, dict(answer.probabilities), "jev", confidence >= self.min_confidence)


# ------------------------------------------------------------------------------------- classifiers

#: Choice labels for the building question -> the key used in `data/campus/campus_map.json`.
BUILDING_LABELS: dict[str, str] = {
    "BRS": "BRS", "CHTM": "CHTM", "EDS": "EDS", "GYMNASIUM": "GYMNASIUM", "MAIN": "MAIN",
    "MAIN INFRASTRUCTURE": "MAIN_INFRA", "PE": "PE", "SCIENCE A": "SCIENCE_A", "ARCHITECTURE": "ARCHITECTURE",
    "SITE": "SITE",
}
#: The inverse: the campus-map key -> the label the options use (so a hint reads like an option).
_LABEL_OF: dict[str, str] = {key: label for label, key in BUILDING_LABELS.items()}
_BUILDING_HELP = {
    "MAIN": "the Main building", "MAIN INFRASTRUCTURE": "the Main Infrastructure building (names start with Main_Infrustructure)",
    "SCIENCE A": "the Science A building (names start with Sciene_A)", "GYMNASIUM": "the Gymnasium building",
    "SITE": "not part of any building: roads, sidewalks, bridges, landscape, loose groups",
}
UNIT_TYPES = ("floor", "stair", "roof", "shell", "road", "landscape", "bridge", "other")
FLOOR_MAX = 15
MATERIAL_CATEGORIES = ("glass", "concrete", "metal", "wood", "stone", "plant", "fabric", "paint", "other")

_GROUP_STATE = {
    "task": "Classify groups of a university campus model by their SketchUp group names and a few numbers.",
    "buildings": list(BUILDING_LABELS),
    "naming": "Group names start with the building (CHTM, EDS, BRS, Gymnasium, Main_Infrustructure, MAIN, PE, "
              "Sciene_A, Architecture); floors are written 1st, 2nd, 3rd, 4th ... or Floor_plan_2; lengths are inches.",
}
_MATERIAL_STATE = {
    "task": "Classify materials of a university campus model by their names, texture file names and base colour.",
    "note": "Material names come from Minecraft block textures and PBR texture packs; kd is the base colour (0-1 RGB).",
}


def _num(x) -> str:
    return "unknown" if x is None else f"{float(x):.1f}"


def classify_group_names(rows: list[dict], decider) -> list[dict]:
    """rows: {"name", "tris", "z_min", "z_max", "footprint_building"}. Per row, four typed questions: the
    building (Choice), the unit type (Choice), the floor number (Score 0-15) and whether it is a duplicate
    copy of another group (Noul). Returns `{"name", "building", "type", "floor", "duplicate"}` per row; the
    building answer is the campus-map key (`MAIN_INFRA`, `SCIENCE_A`)."""
    questions: dict[str, Any] = {}
    for i, row in enumerate(rows):
        fact = (f"The SketchUp group named '{row['name']}' has {row.get('tris', 'an unknown number of')} triangles, "
                f"lowest point z={_num(row.get('z_min'))} in, highest z={_num(row.get('z_max'))} in, and its footprint lies "
                f"mostly in the footprint of {_LABEL_OF.get(row.get('footprint_building'), row.get('footprint_building')) or 'no building'}.")
        questions[f"{i}:building"] = ChoiceQ(
            f"{fact} Which building does this group belong to?",
            {label: _BUILDING_HELP.get(label) for label in BUILDING_LABELS})
        questions[f"{i}:type"] = ChoiceQ(
            f"{fact} What kind of piece is this group?",
            {"floor": "one storey of a building (slab, walls, rooms)", "stair": "a staircase or emergency stairs",
             "roof": "a roof", "shell": "a facade or outer shell piece", "road": "a road or sidewalk",
             "landscape": "ground, trees, plants or terrain", "bridge": "a bridge or walkway",
             "other": "anything else"})
        questions[f"{i}:floor"] = ScoreQ(
            f"{fact} Which floor number does the name say? 0 if it names no floor.",
            [f"floor {n}" if n else "no floor / ground level" for n in range(FLOOR_MAX + 1)])
        questions[f"{i}:duplicate"] = NoulQ(
            f"{fact} Is this group a duplicate copy of another group, judging by the name (a trailing digit, "
            f"'copy', 'obj1', '#1')?")
    decisions = decider.ask(_GROUP_STATE, questions)
    out = []
    for i, row in enumerate(rows):
        building = decisions[f"{i}:building"]
        if building.answer is not None:
            building.answer = BUILDING_LABELS.get(building.answer, building.answer)
            building.probabilities = {BUILDING_LABELS.get(k, k): v for k, v in building.probabilities.items()}
        out.append({"name": row["name"], "building": building, "type": decisions[f"{i}:type"],
                    "floor": decisions[f"{i}:floor"], "duplicate": decisions[f"{i}:duplicate"]})
    return out


def classify_materials(names: list, decider) -> list[dict]:
    """names: material names, or dicts `{"name", "texture", "kd"}` (texture is the file name only). Per
    material: the category (Choice) and whether it is a trim or patch material (Noul). Returns
    `{"name", "category", "trim"}` per material."""
    questions: dict[str, Any] = {}
    resolved = []
    for i, item in enumerate(names):
        info = item if isinstance(item, dict) else {"name": item}
        resolved.append(info["name"])
        fact = f"The material is named '{info['name']}'."
        if info.get("texture"):
            fact += f" Its texture file is named '{info['texture']}'."
        else:
            fact += " It has no texture."
        if info.get("kd") is not None:
            fact += " Its base colour (RGB 0-1) is " + ", ".join(f"{float(c):.2f}" for c in info["kd"]) + "."
        questions[f"{i}:category"] = ChoiceQ(
            f"{fact} Which kind of surface is this material?",
            {c: None for c in MATERIAL_CATEGORIES})
        questions[f"{i}:trim"] = NoulQ(
            f"{fact} Is it a trim or patch material, a small accent used for edges, borders, frames or fixes, "
            f"rather than a main surface?")
    decisions = decider.ask(_MATERIAL_STATE, questions)
    return [{"name": name, "category": decisions[f"{i}:category"], "trim": decisions[f"{i}:trim"]}
            for i, name in enumerate(resolved)]
