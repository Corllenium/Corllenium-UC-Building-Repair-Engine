"""The HTTP app of `uc-fixer-decide`. nginx sets X-Remote-User after its basic-auth check; two roles come from it:
the engine (`cfg.engine_user`) and the owner (`cfg.owner_users`). No secret is read, logged or returned here:
a failed Jev call is reported as its class name only."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from decide_service import logic
from engine.decide import wire

#: Columns that stay on the server: the dedupe key and the question's state (can be large, not the owner's concern).
HIDDEN = ("key", "state", "state_json")
LIMIT_MAX = 500
LIMIT_DEFAULT = 100


# ------------------------------------------------------------------------------------- request shapes


class AskBody(BaseModel):
    state: dict | str
    questions: dict[str, dict]


class ReviewBody(BaseModel):
    accept: bool = False
    answer: Any = None


class ImportItem(BaseModel):
    state: dict | str
    question: dict
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


def _questions(raw: dict[str, dict]) -> dict:
    """The wire questions as question objects; a malformed one is a 422 (before any logic runs)."""
    out = {}
    for qid, spec in raw.items():
        try:
            out[qid] = wire.question_from_json(spec)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise HTTPException(422, f"question {qid[:60]!r} is not a valid question") from None
    return out


# ------------------------------------------------------------------------------------- the app


def create_app(store, cfg, make_decider) -> FastAPI:
    app = FastAPI(title="uc-fixer-decide", docs_url=None, redoc_url=None, openapi_url=None)
    owner, engine, either = _role(cfg)

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
        offset = max(0, offset)
        rows = store.list(status=status, qtype=type, min_conf=min_conf, q=q, limit=limit, offset=offset)
        return {"items": [_public(r) for r in rows], "counts": store.counts(type)}

    @app.post("/api/decide/review/{id}")
    def review(id: int, body: ReviewBody, user: str = Depends(owner)):
        if not body.accept and "answer" not in body.model_fields_set:
            raise HTTPException(422, "send {\"accept\": true} or {\"answer\": value}")
        try:
            row = logic.review(store, id, user, accept=body.accept, answer=body.answer)
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
            raise HTTPException(502, f"jev call failed: {exc}") from None
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
                "daily_token_cap": cfg.daily_token_cap}

    return app
