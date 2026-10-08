## Global Constraints

- AGENTS.md binds every task: test first; commit after every item; stage files by name; never a bare `cd`; Python is
  `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"`, run from the worktree root in a subshell with
  `PYTHONPATH` set.
- **Branches:** the integration branch `feat/jev-vps` comes from `feat-dashboard` (8b22e75 or later). Each job is
  `claude/<id>` in `.claude/worktrees/<id>` from `feat/jev-vps`. The controller merges with `--no-ff` after a review,
  and asks the repair-engine session before any merge into `feat-dashboard`.
- **Jev is off:** default `DECIDE_JEV_ENABLED=false`. No task makes a real Jev call. Every test uses a fake client.
- **Secrets:** the TypeSafe key is read from the environment only (service). The `uc-engine` password is
  `UC_DECIDE_PASSWORD`, from the environment or else only that one line of the git-ignored repo-root `.env`
  (engine). Neither is ever printed, logged, put in a `repr` or exception text, or committed. Agents never open `.env*`.
- **Never touch:** the live containers `fixer-api`, `fixer-web`, `fixer-db`; the database `fixer`; the VPS. Every test
  database is a throwaway container named `decide-test-pg` on port 55432.
- **The pipeline never waits:** `RemoteDecider` has a 10 s timeout and no retries. Any failure gives `none` / `error`
  decisions, never accepted.
- **Only text leaves the PC:** names, texture file names, categories, small numbers.
- **Limits:** a Score has at most 10 levels and a Choice at most 255 options (`check_question_limits`). The daily cap is
  1,000,000 tokens (`DECIDE_DAILY_TOKEN_CAP`).
- **Logins:** the engine login is `uc-engine`. The owner logins come from `DECIDE_OWNER_USERS` (default `gab`). The
  user name arrives in `X-Remote-User`, set by nginx.
- **Out of scope:** the actual VPS deploy (the controller does it with the owner's OK at that moment), switching Jev
  on, P1-D2, the `repair.next_step` question.


### Task J5: the image, the VPS stack files and the runbook

**Files:**
- Create: `deploy/vps/decide/decide_service/main.py`, `deploy/vps/decide/Dockerfile`,
  `deploy/vps/decide/requirements.txt`
- Modify: `deploy/vps/docker-compose.yml`, `deploy/vps/nginx.conf`, `deploy/vps/README.md`
- Test: `deploy/vps/decide/tests/test_main.py`, plus the container smoke run in Step 4

**Interfaces:**
- Consumes: `create_app`, `PostgresStore`, `Settings` (J2-J4).
- Produces: the image `ucmodelfixer-decide:vps`, listening on port 8200 inside the network `internal`.

- [ ] **Step 1: Write the failing test** `test_main.py`. With the environment set (`DECIDE_DATABASE_URL` for the
  memory store, `DECIDE_JEV_ENABLED` unset), `main.build_app(store_factory=lambda url: MemoryStore())` returns an app
  whose health says `jev_enabled: false`. `main.make_decider()` builds `JevDecider(env_file=Path("/nonexistent"),
  min_confidence=cfg.min_confidence)`, so the key comes from the environment only. Assert that its `available` follows
  `TYPESAFE_API_KEY` set or unset, using a fake value, and that `repr` never shows it.
- [ ] **Step 2: Implement `main.py`** (`build_app`, `make_decider`, and `app = build_app()` guarded by
  `if os.environ.get("DECIDE_DATABASE_URL")`), `requirements.txt` (`fastapi>=0.115`, `uvicorn[standard]>=0.30`,
  `psycopg[binary]>=3.2`, `typesafe-sdk>=0.7.2,<0.8`) and the `Dockerfile`, built from the repo root:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY deploy/vps/decide/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY engine/__init__.py /app/engine/__init__.py
COPY engine/decide /app/engine/decide
COPY deploy/vps/decide/decide_service /app/decide_service
COPY deploy/vps/decide/schema.sql /app/schema.sql
ENV PYTHONPATH=/app
EXPOSE 8200
CMD ["uvicorn", "decide_service.main:app", "--host", "0.0.0.0", "--port", "8200"]
```

  `main.build_app` calls `PostgresStore(url).ensure_schema()` once at start.
- [ ] **Step 3: The stack files.**
  - `docker-compose.yml`: add the service `decide`. It uses `image: ucmodelfixer-decide:vps`,
    `container_name: uc-fixer-decide` and `env_file: ./decide.env`, with this `environment`:
    `DECIDE_DATABASE_URL: postgresql://fixer:fixer@uc-fixer-db:5432/fixer`, `DECIDE_JEV_ENABLED: "false"`,
    `DECIDE_OWNER_USERS: gab`. It has `depends_on: db: condition: service_healthy`, `networks: [internal]`,
    `restart: unless-stopped`, and no published ports.
  - `nginx.conf`: put this before `location /api/`:

```nginx
    location /api/decide/ {
        proxy_pass http://uc-fixer-decide:8200;
        proxy_read_timeout 60s;
        proxy_set_header Host $host;
        proxy_set_header X-Remote-User $remote_user;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location = /api/decide/ask {
        if ($remote_user != "uc-engine") { return 403; }
        proxy_pass http://uc-fixer-decide:8200;
        proxy_set_header X-Remote-User $remote_user;
    }
```

  - `README.md`: a section **"Jev service (uc-fixer-decide)"**. It holds:
    - what the service does;
    - that Jev is off by default;
    - the owner's prompted commands: the `uc-engine` login (the same `htpasswd -B` command without `-c`, user
      `uc-engine`), and `decide.env`, written by
      `ssh -t … "read -rs -p 'TypeSafe key: ' K; umask 077; printf 'TYPESAFE_API_KEY=%s\n' \"\$K\" > /docker/uc-fixer/decide.env"`;
    - the image load (`docker save ucmodelfixer-decide:vps | ssh … docker load`);
    - how to switch Jev on later (add `DECIDE_JEV_ENABLED=true` to `decide.env`, then `docker compose up -d decide`,
      each with the owner's OK);
    - the rollback (`docker compose rm -sf decide`; the schema `decide` stays unless the owner asks for it to be
      dropped).
- [ ] **Step 4: Build and smoke-run on the PC**, never touching the `fixer-*` containers:
  - `docker build -f deploy/vps/decide/Dockerfile -t ucmodelfixer-decide:vps .`
  - `docker network create decide-smoke`
  - `docker run -d --rm --name decide-smoke-db --network decide-smoke -e POSTGRES_PASSWORD=test postgres:16-alpine`
  - wait for `docker exec decide-smoke-db pg_isready`
  - `docker run -d --rm --name decide-smoke --network decide-smoke -p 58200:8200 -e DECIDE_DATABASE_URL=postgresql://postgres:test@decide-smoke-db:5432/postgres ucmodelfixer-decide:vps`
  - `curl -s -H "X-Remote-User: gab" http://localhost:58200/api/decide/health` → expected
    `{"ok":true,"jev_enabled":false,...}`
  - then stop both containers and remove the network.
- [ ] **Step 5: Commit:** `feat(decide-service): image, VPS compose service, nginx route, runbook (Jev off by default)`.

---

