"""The HTTP app of `uc-fixer-decide`. nginx sets X-Remote-User after its basic-auth check; two roles come from it:
the engine (`cfg.engine_user`) and the owner (`cfg.owner_users`). No secret is read, logged or returned here:
a failed Jev call is reported as its class name only."""
from __future__ import annotations

import logging
import re
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictBool, StrictStr, model_validator

from decide_service import logic
from engine.decide import wire
from engine.decide.jev import MODEL

log = logging.getLogger(__name__)

#: Columns that stay on the server: the dedupe key and the question's state (can be large, not the owner's concern).
HIDDEN = ("key", "state", "state_json")
LIMIT_MAX = 500
LIMIT_DEFAULT = 100
OFFSET_MAX = 2 ** 31
#: The only RuntimeError texts that reach a 502 body: a class name with an optional HTTP status, or "no answer".
_SAFE_502 = re.compile(r"^[A-Za-z]+( status=\d+)?$")


# ------------------------------------------------------------------------------------- request shapes


class QuestionIn(BaseModel):
    """A question on the wire, strictly typed (the same shape as wire.question_to_json)."""
    kind: Literal["noul", "choice", "score"]
    instructions: StrictStr
    criteria: dict[StrictStr, StrictStr | None] | list[StrictStr] | None = None
    qtype: StrictStr = ""
    subject: StrictStr = ""

    @model_validator(mode="after")
    def _criteria_fit_the_kind(self):
        if self.kind == "noul" and self.criteria is not None:
            raise ValueError("a noul question has no criteria")
        if self.kind == "choice" and not (isinstance(self.criteria, dict) and self.criteria):
            raise ValueError("a choice question needs a non-empty object of options")
        if self.kind == "score" and not (isinstance(self.criteria, list) and self.criteria):
            raise ValueError("a score question needs a non-empty list of levels")
        return self


class AskBody(BaseModel):
    state: dict | str
    questions: dict[str, QuestionIn]


class ReviewBody(BaseModel):
    accept: StrictBool | None = None
    answer: Any = None


class ImportItem(BaseModel):
    state: dict | str
    question: QuestionIn
    answer: Any = None
    confidence: Any = None
    probabilities: dict | None = None
    model: str | None = None


class ImportBody(BaseModel):
    items: list[ImportItem]


# ------------------------------------------------------------------------------------- roles


def _user(request: Request) -> str:
    user = request.headers.get("X-Remote-User", "")
    if not user:
        raise HTTPException(401, "no user")
    return user


def _role(cfg):
    def owner(user: str = Depends(_user)) -> str:
        if user not in cfg.owner_users:
            raise HTTPException(403, "owner only")
        return user

    def engine(user: str = Depends(_user)) -> str:
        if user != cfg.engine_user:
            raise HTTPException(403, "engine only")
        return user

    def either(user: str = Depends(_user)) -> str:
        if user != cfg.engine_user and user not in cfg.owner_users:
            raise HTTPException(403, "unknown user")
        return user

    return owner, engine, either


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in HIDDEN}


def _questions(raw: dict[str, QuestionIn]) -> dict:
    """The validated wire questions as question objects."""
    return {qid: wire.question_from_json(spec.model_dump()) for qid, spec in raw.items()}


# ------------------------------------------------------------------------------------- the app


def create_app(store, cfg, make_decider) -> FastAPI:
    app = FastAPI(title="uc-fixer-decide", docs_url=None, redoc_url=None, openapi_url=None)
    owner, engine, either = _role(cfg)

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError):
        # only where and why, never the input: a bad field may hold something the caller must not see echoed
        return JSONResponse({"detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                                        for e in exc.errors()]}, status_code=422)

    @app.middleware("http")
    async def _no_leaks(request: Request, call_next):
        # A middleware, not exception_handler(Exception): Starlette re-raises after that handler, and the server
        # would then log the traceback with the exception's message (a DSN, a key).
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001
            log.error("unhandled %s", type(exc).__name__)
            return JSONResponse({"detail": "internal error"}, status_code=500)

    @app.post("/api/decide/ask")
    def ask(body: AskBody, _: str = Depends(engine)):
        questions = _questions(body.questions)
        try:
            answers = logic.answer(store, cfg, make_decider, body.state, questions)
        except ValueError as exc:                       # a limit breach (check_question_limits)
            raise HTTPException(400, str(exc)) from None
        return {"answers": answers}

    @app.get("/api/decide/suggestions")
    def suggestions(status: str | None = None, type: str | None = None, min_conf: float | None = None,
                    q: str | None = None, limit: int = LIMIT_DEFAULT, offset: int = 0,
                    _: str = Depends(owner)):
        limit = max(1, min(LIMIT_MAX, limit))
        offset = min(max(0, offset), OFFSET_MAX)
        rows = store.list(status=status, qtype=type, min_conf=min_conf, q=q, limit=limit, offset=offset)
        return {"items": [_public(r) for r in rows], "counts": store.counts(type)}

    @app.post("/api/decide/review/{id}")
    def review(id: int, body: ReviewBody, user: str = Depends(owner)):
        has_answer = "answer" in body.model_fields_set
        if body.accept is not None and has_answer:
            raise HTTPException(422, "send accept or answer, not both")
        if body.accept is not True and not has_answer:
            raise HTTPException(422, "send {\"accept\": true} or {\"answer\": value}")
        try:
            row = logic.review(store, id, user, accept=body.accept is True, answer=body.answer)
        except KeyError:
            raise HTTPException(404, "unknown suggestion") from None
        except ValueError as exc:                       # not one of the question's options
            raise HTTPException(422, str(exc)) from None
        return _public(row)

    @app.post("/api/decide/reask/{id}")
    def reask(id: int, _: str = Depends(owner)):
        try:
            row = logic.reask(store, cfg, make_decider, id)
        except PermissionError as exc:                  # "jev off" | "daily cap"
            raise HTTPException(409, str(exc)) from None
        except KeyError:
            raise HTTPException(404, "unknown suggestion") from None
        except RuntimeError as exc:                     # logic gives the class name only, never a message with a key
            text = str(exc)
            ok = _SAFE_502.fullmatch(text) or text == "no answer"
            raise HTTPException(502, f"jev call failed: {text}" if ok else "jev call failed") from None
        return _public(row)

    @app.get("/api/decide/confirmed")
    def confirmed(type: str, _: str = Depends(either)):
        return {"type": type, "answers": store.confirmed(type)}

    @app.post("/api/decide/import")
    def import_(body: ImportBody, _: str = Depends(engine)):
        items = [it.model_dump(exclude_unset=True) for it in body.items]
        return logic.import_items(store, items)

    @app.get("/api/decide/health")
    def health(_: str = Depends(either)):
        return {"ok": True, "jev_enabled": cfg.jev_enabled, "tokens_today": store.tokens_today(),
                "daily_token_cap": cfg.daily_token_cap, "model": MODEL}

    return app
