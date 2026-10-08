"""`RemoteDecider`: the engine's client of the VPS service `uc-fixer-decide`.

It has the same `.ask(state, questions) -> dict[str, Decision]` as `JevDecider`, so `classify_group_names`,
`classify_materials` and the pilot use it unchanged. The service holds the TypeSafe key, the cache and the
owner's review queue; this client holds only the `uc-engine` password.

- The pipeline never waits. One HTTP call per `ask`, a timeout (10 s by default) that is also a whole-call
  deadline, and no retries. Every failure gives decisions that are never accepted:
    - a network error or a timeout gives `source="none"` and `error` = the exception class name;
    - a non-2xx answer gives `source="error"` and `error="HTTP <status>"`.
- Only text leaves the machine (the same questions `JevDecider` would send). `jev.check_question_limits` runs
  locally first and raises `ValueError`, as it does for `JevDecider`.
- The password (`UC_DECIDE_PASSWORD`) comes from the process environment first, else ONLY that one line of the
  env file (`jev.read_env_var`). It is sent only in the Basic `Authorization` header, never put into
  `os.environ`, and never printed, logged, `repr`ed, recorded in `.calls` or put into an exception message: a
  failure records the exception's class name or the HTTP status only. A response body is never read on an
  error and never logged.
- HTTPS is required for any host but the local machine, and redirects are not followed (a redirect would
  carry the header to another place).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from engine.decide import jev, wire
from engine.decide.jev import Decision, _failed, _none, check_question_limits

log = logging.getLogger(__name__)

PASSWORD_VAR = "UC_DECIDE_PASSWORD"
DEFAULT_USER = "uc-engine"
ASK_PATH = "/api/decide/ask"
CONFIRMED_PATH = "/api/decide/confirmed"
#: A reply bigger than this is refused (the service answers a few KB per question).
MAX_REPLY_BYTES = 32 * 1024 * 1024
_LOOPBACK = ("localhost", "127.0.0.1", "::1")
_QTYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class _Status(Exception):
    """A non-2xx reply. Carries the status only, never the body."""

    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


class _BadReply(Exception):
    """A 2xx reply that is too large or not JSON."""


def _error_name(exc: BaseException) -> str:
    if isinstance(exc, _Status):
        return f"HTTP {exc.status}"
    return "BadReply" if isinstance(exc, _BadReply) else type(exc).__name__


def _served(error: str) -> bool:
    """The service answered (with an error status or a bad body): "error". Otherwise the call never got an
    answer (network error, timeout): "none"."""
    return error.startswith("HTTP ") or error == "BadReply"


class RemoteDecider:
    """Asks the VPS service typed questions. Same `.ask` as `JevDecider`; never waits past `timeout`."""

    def __init__(self, url: str, user: str = DEFAULT_USER, password: str | None = None, timeout: float = 10.0, *,
                 env_file: Path | str | None = None):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("RemoteDecider needs an http(s) URL with a host")
        if parts.scheme == "http" and parts.hostname not in _LOOPBACK:
            raise ValueError("RemoteDecider sends a password: use https (plain http only for localhost)")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.url = url.rstrip("/")
        self.user = user
        self.timeout = float(timeout)
        #: One entry per HTTP call: path, questions, ok, status, latency_s, error.
        self.calls: list[dict] = []
        env_path = Path(env_file) if env_file is not None else jev.DEFAULT_ENV_FILE
        self._password: str | None = (password or os.environ.get(PASSWORD_VAR)
                                      or jev.read_env_var(env_path, PASSWORD_VAR) or None)

    def __repr__(self) -> str:
        return f"RemoteDecider(url={self.url!r}, user={self.user!r}, available={self.available}, timeout={self.timeout})"

    @property
    def available(self) -> bool:
        """A password is set."""
        return self._password is not None

    # ---------------------------------------------------------------------------------- transport

    def _auth(self) -> str:
        return "Basic " + base64.b64encode(f"{self.user}:{self._password}".encode("utf-8")).decode("ascii")

    def _send(self, method: str, path: str, payload: bytes | None):
        """One HTTP call. Returns the parsed JSON of a 2xx reply; raises `_Status` for any other status."""
        headers = {"Authorization": self._auth(), "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url + path, data=payload, headers=headers, method=method)
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read(MAX_REPLY_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise _Status(status) from None
        if len(raw) > MAX_REPLY_BYTES:
            raise _BadReply
        try:
            return json.loads(raw)
        except ValueError:
            raise _BadReply from None

    def _call(self, method: str, path: str, body: dict | None, questions: int = 0):
        """`_send` under a whole-call deadline, recorded in `.calls`. Returns `(reply, error)`; `error` is ""
        or a class name / "HTTP <status>"; `status` is kept in the call entry."""
        entry = {"path": path.split("?")[0], "questions": questions, "ok": False, "status": None,
                 "latency_s": 0.0, "error": ""}
        t0 = time.perf_counter()
        box: dict = {}

        def run():
            try:
                box["reply"] = self._send(method, path, None if body is None else json.dumps(body).encode("utf-8"))
            except BaseException as exc:  # noqa: BLE001 -- handed to the caller's thread below
                box["exc"] = exc

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(self.timeout + 0.25)
        reply, error = None, ""
        if worker.is_alive():
            error = "TimeoutError"                    # the thread is a daemon: it dies with its socket
        elif "exc" in box:
            exc = box["exc"]
            error = _error_name(exc)
            if isinstance(exc, _Status):
                entry["status"] = exc.status
        else:
            reply = box["reply"]
            entry["status"], entry["ok"] = 200, True
        entry["latency_s"] = round(time.perf_counter() - t0, 4)
        entry["error"] = error
        self.calls.append(entry)
        if error:
            log.warning("decide call failed: %s %s, %s, %.2fs", method, entry["path"], error, entry["latency_s"])
        else:
            log.debug("decide call ok: %s %s, %d questions, %.2fs", method, entry["path"], questions,
                      entry["latency_s"])
        return reply, error

    # ---------------------------------------------------------------------------------- ask

    def ask(self, state: str | dict, questions: dict) -> dict[str, Decision]:
        check_question_limits(questions)      # a malformed question is a bug: raise to the caller, send nothing
        if not self.available:
            return {qid: _none() for qid in questions}
        if not questions:
            return {}
        try:
            body = {"state": {"text": state} if isinstance(state, str) else state,
                    "questions": {qid: wire.question_to_json(q) for qid, q in questions.items()}}
            json.dumps(body)
        except Exception as exc:  # noqa: BLE001 -- a state that is not JSON: nothing is sent
            return {qid: _failed(type(exc).__name__) for qid in questions}
        reply, error = self._call("POST", ASK_PATH, body, len(questions))
        if error:
            # a network error or timeout is "none"; the service answering badly is "error"
            make = _failed if _served(error) else (lambda e: Decision(None, 0.0, {}, "none", False, e))
            return {qid: make(error) for qid in questions}
        answers = reply.get("answers") if isinstance(reply, dict) else None
        if not isinstance(answers, dict):
            return {qid: _failed("BadReply") for qid in questions}
        out: dict[str, Decision] = {}
        for qid in questions:
            try:
                out[qid] = wire.decision_from_json(answers[qid])
            except Exception as exc:  # noqa: BLE001 -- a missing or malformed answer
                out[qid] = _failed("MissingAnswer" if isinstance(exc, KeyError) else type(exc).__name__)
        return out

    # ---------------------------------------------------------------------------------- confirmed

    def confirmed(self, qtype: str) -> dict:
        """The owner-confirmed `{subject: answer}` for one question type. Raises `RuntimeError` (class name or
        HTTP status only) when it cannot be fetched."""
        if not _QTYPE.match(qtype or ""):
            raise ValueError("the question type must be letters, digits, '.', '_' or '-'")
        if not self.available:
            raise RuntimeError(f"no {PASSWORD_VAR} (environment or env file)")
        reply, error = self._call("GET", f"{CONFIRMED_PATH}?type={urllib.parse.quote(qtype, safe='')}", None)
        if error:
            raise RuntimeError(f"confirmed answers not fetched: {error}")
        answers = reply.get("answers") if isinstance(reply, dict) else None
        if not isinstance(answers, dict):
            raise RuntimeError("confirmed answers not fetched: BadReply")
        return answers


def pull_confirmed(url: str, qtype: str, out_dir: Path | str, *, user: str = DEFAULT_USER,
                   password: str | None = None, timeout: float = 10.0, env_file: Path | str | None = None) -> Path:
    """Fetch the owner-confirmed answers of one question type and write `<out_dir>/<qtype>.json` as
    `{subject: answer}`. Raises `ValueError` for a bad type or URL and `RuntimeError` for a failed fetch;
    nothing is written then."""
    if not _QTYPE.match(qtype or ""):
        raise ValueError("the question type must be letters, digits, '.', '_' or '-'")
    answers = RemoteDecider(url, user, password, timeout, env_file=env_file).confirmed(qtype)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{qtype}.json"
    tmp = out_dir / f".{qtype}.json.tmp"
    tmp.write_text(json.dumps(answers, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path
