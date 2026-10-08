# Task J6 report: RemoteDecider and decide-pull

Branch `claude/J6` (worktree `.claude/worktrees/J6`, base 771ab30). Status: DONE_WITH_CONCERNS (concerns below are design notes, nothing failing).

## Commits
- `091e0e2` feat(decide): RemoteDecider (same ask as JevDecider, never waits), pull_confirmed, jev.read_env_var
- `9d0a3f6` feat(decide): decide-pull CLI writes the owner-confirmed answers of one type to data/decide/confirmed

## Item 1: helper + RemoteDecider + pull_confirmed (`engine/decide/remote.py`, `jev.read_env_var`)
Tests: `engine/tests/test_decide_remote.py` (32 tests, local `http.server` in a thread, fake password only).

Red (before `remote.py` existed):
```
engine\tests\test_decide_remote.py:18: in <module>
    from engine.decide.remote import RemoteDecider, pull_confirmed
E   ModuleNotFoundError: No module named 'engine.decide.remote'
ERROR engine/tests/test_decide_remote.py
1 error in 0.44s
```
Green (non-CLI tests, after implementation): `29 passed, 3 deselected in 8.07s`.

## Item 2: CLI `decide-pull`
Red (before the subcommand):
```
python -m engine.cli: error: argument command: invalid choice: 'decide-pull' (choose from fix, ..., decide-pilot)
FAILED test_cli_decide_pull_writes_the_file
FAILED test_cli_decide_pull_reads_the_password_line_of_the_env_file
FAILED test_cli_decide_pull_failure_returns_2_and_prints_no_secret
3 failed, 29 deselected in 3.13s
```
Green, the four decide test files:
```
88 passed in 10.84s
```

## Full engine suite (once, at the end)
```
.................................................x...................... [ 86%]
........................................................................ [ 92%]
........................................................................ [ 98%]
.....................                                                    [100%]
1244 passed, 1 xfailed in 687.50s (0:11:27)
```

## What it does (matches the service contract in app.py)
- `ask`: `check_question_limits` first (raises `ValueError`, even with no password, nothing sent); no password gives all `none`, no request, no `.calls`; else one `POST {url}/api/decide/ask` with `{"state", "questions": {qid: wire.question_to_json}}` (a str state becomes `{"text": ...}`), Basic auth `uc-engine`; answers mapped with `wire.decision_from_json` (the extra `suggestion_id` is ignored).
- Non-2xx (400/401/403/409/422/5xx, and any 3xx since redirects are not followed): every decision `source="error"`, `error="HTTP <status>"`, never accepted; exactly one request (tested for 400, 401, 403, 409, 422, 500, 502 with a body that echoes the password).
- Network error or timeout: every decision `source="none"`, `error` = exception class name. The timeout is also a whole-call deadline (worker thread joined at `timeout + 0.25 s`), so a server that drips bytes cannot stretch it (tested: sleeping server and dripping server both end within timeout + 1 s).
- A 2xx body that is not JSON / has no `answers` / lacks a qid gives `source="error"` with `BadReply` / `MissingAnswer`.
- `.calls` entries: `path, questions, ok, status, latency_s, error`.
- Password: explicit arg, else `UC_DECIDE_PASSWORD` in the environment, else ONLY that line of the env file via the new `jev.read_env_var(path, name)`; `read_env_key` now delegates to it (all existing jev tests pass unchanged). Never put in `os.environ`. Tests assert it is absent from `repr`, `str`, caplog at DEBUG, `.calls`, decisions, and exception text of the constructor and `pull_confirmed` failures, and that the Base64 form is absent too.
- `pull_confirmed(url, qtype, out_dir, *, user, password, timeout, env_file) -> Path`: `GET /api/decide/confirmed?type=...`, writes `<out_dir>/<qtype>.json` atomically as `{subject: answer}`. A qtype that is not `[A-Za-z0-9][A-Za-z0-9._-]*` raises `ValueError` before any request (no path traversal). Failures raise `RuntimeError` with the class name or `HTTP <status>` only and write nothing.
- CLI `decide-pull --url --type [--out data/decide/confirmed] [--env-file]`: exit 0, or 2 with `error: ...` on stderr (no secret).
- `classify_materials(items, RemoteDecider(...))` works unchanged (tested, success and 500).

## Concerns and design notes (said plainly)
1. **Addition beyond the brief:** `RemoteDecider` raises `ValueError` at construction for plain `http://` to any host but localhost/127.0.0.1/::1, and for non-http(s) schemes, because Basic auth over plaintext would leak the password. Spec says HTTPS, so this should be harmless; if the controller wants a plain-http docker-network URL it has to be loosened.
2. **Redirects are not followed** (the Authorization header would follow them); a 3xx is `HTTP <status>`. nginx on the VPS should not redirect an API path, but an http->https redirect would surface as `HTTP 301`: give the https URL.
3. `url` is the service base (`https://host`), the client appends `/api/decide/...`. If the nginx route is mounted under another prefix, the URL would need that prefix before `/api/decide`... which cannot work with the fixed path; unverified against the deployed nginx (not in my scope).
4. The refused-connection test takes about 2 s on Windows (connect to a closed port); the whole file runs in about 8 s.
5. No Jev or network beyond 127.0.0.1 was used; the real `.env` was never opened (the default env file is monkeypatched in every test). `engine/guard/**`, `FixProfile` and existing tests are untouched. No geometry change, so the Validator run does not apply.

## Review round (J6 APPROVED with Minors): commit 35b120b
Tests first: the new tests were added, run, and failed (3 FAILED: userinfo, 2xx status, accepted; 6 ERROR: the CLI tests, which need `engine.cli.DATA_DIR`), then green.
1. `RemoteDecider` raises `ValueError` for a URL with userinfo (user or password), text without the value. Test: `test_a_url_with_userinfo_is_refused_without_echoing_it`.
2. `wire.decision_from_json`: `accepted = d.get("accepted") is True` ("false", "true", 1, "yes", None, 0 all give False). Test: `test_accepted_is_true_only_for_the_json_true` (also through the client). Existing wire tests pass.
3. `decide-pull`: default `--out` is `<repo>/data/decide/confirmed` (repo = dir with pyproject.toml, `engine.cli.DATA_DIR`, independent of the cwd); an `--out` that resolves outside `DATA_DIR` exits 2 with a clear error before any request. The 3 older CLI tests now write under a tmp `DATA_DIR` (monkeypatched). Tests: `..._default_out_is_anchored_...`, `..._refuses_an_out_outside_...`.
4. `--url` is optional; falls back to `UC_DECIDE_URL`; neither gives exit 2 "no service URL: pass --url or set UC_DECIDE_URL"; the flag wins over the variable. Test: `..._url_falls_back_to_uc_decide_url_and_else_errors`.
5. `.calls[..]["status"]` is the real `resp.status` (also kept on a BadReply). Test: `test_calls_record_the_real_2xx_status` (201).
6. Comment corrected: the hung worker keeps its socket until the server ends the response (nginx `proxy_read_timeout` 60 s bounds it) and never blocks the pipeline.

Run: `engine/tests/test_decide_remote.py test_decide_wire.py test_decide_jev.py test_decide_pilot.py` = 94 passed; with `engine/tests/test_cli.py` added = 154 passed. The full engine suite was not re-run after this round (it takes about 11 minutes; the changes touch only remote.py, wire.py and the decide-pull branch of cli.py, plus new module-level `DATA_DIR`/`_repo_root` and `import os` in cli.py).
