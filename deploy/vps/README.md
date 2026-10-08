# UC Model Fixer on the Corllenium VPS (view only)

- **URL:** https://uc-fixer.srv1866850.hstgr.cloud. It is served through the existing Traefik, with a Let's Encrypt
  certificate.
- **Box:** `root@187.127.213.243` (srv1866850). The stack lives in `/docker/uc-fixer`: containers `uc-fixer-db`,
  `uc-fixer-api` and `uc-fixer-web`.
- **Login:** nginx basic auth from `/docker/uc-fixer/users.htpasswd`. While that file is empty, every page answers 401.
- **View only:** the API accepts GET only, so imports, fix runs, error recomputes and verdict writes get 403. The
  engine never runs on the 2 vCPU box; fixing stays on the owner's PC.
- **First deploy:** 2026-10-08, by Claude, at the owner's OK. Images `ucmodelfixer-api:vps` and `ucmodelfixer-web:vps`
  were saved from the PC's live images. The database was restored from a `pg_dump` (6 versions, 30 assets).
  `data/` holds snapshots, errors, errors_doc, meshbuf, fixed and output.

## Set or change the login (owner, PowerShell)
```powershell
ssh -t -i $env:USERPROFILE\.ssh\uc_vps_ed25519 root@187.127.213.243 "docker run --rm -it -v /docker/uc-fixer:/w httpd:2.4-alpine htpasswd -B -c /w/users.htpasswd gab"
```
It prompts for the password twice and stores only a bcrypt hash. nginx re-reads the file on every request, so no
restart is needed.

## Update the data from the PC
1. `docker exec fixer-db pg_dump -U fixer -d fixer -Fc > fixer.dump`
2. `tar --force-local -czf data.tar.gz -C data snapshots errors errors_doc meshbuf fixed output`
3. `scp` both to `/docker/uc-fixer/`, then on the box:
   - `tar -xzf data.tar.gz -C data`;
   - `docker cp fixer.dump uc-fixer-db:/tmp/`;
   - `docker exec uc-fixer-db pg_restore -U fixer -d fixer --clean --no-owner /tmp/fixer.dump`.

## Jev service (uc-fixer-decide)
**What it does.** A small service that stores the repair engine's soft questions (which category is this material,
which group is a wall, and so on) and, only when switched on, asks Jev for a suggestion. It keeps every answer and
shows them to the owner for review. Its tables live in the schema `decide` of the same database `fixer`; it does not
touch the dashboard's tables. Only text reaches it: names, texture file names, categories, small numbers.

**Jev is off by default.** With it off, the engine's questions come back as "none / jev off" and nothing calls the
TypeSafe API. Nothing here makes a Jev call until the owner switches it on (below).

**Who may call what.** `https://uc-fixer.srv1866850.hstgr.cloud/api/decide/...` sits behind the same nginx login.
nginx puts the login name in `X-Remote-User` and replaces any value the client sends. The container publishes no
port, so nothing else can reach it.
- `uc-engine` (the PC's repair engine): `ask` and `import`, and it may read `confirmed` and `health`.
- `gab` (owner): review, re-ask, suggestions, `confirmed`, `health`.
- `/api/decide/ask` answers 403 to every login but `uc-engine`.

### One-time setup (owner, PowerShell; each command prompts, nothing secret goes on a command line)
1. The engine's login (the same command as above without `-c`, so `gab` stays). It prompts twice:
```powershell
ssh -t -i $env:USERPROFILE\.ssh\uc_vps_ed25519 root@187.127.213.243 "docker run --rm -it -v /docker/uc-fixer:/w httpd:2.4-alpine htpasswd -B /w/users.htpasswd uc-engine"
```
   The same password goes into the PC's git-ignored repo-root `.env` as the line `UC_DECIDE_PASSWORD=...`, typed by
   the owner by hand.
2. The key file `decide.env` (mode 600). It prompts for the TypeSafe key without echo. The file must exist before the
   service starts, because the compose file reads it:
```powershell
ssh -t -i $env:USERPROFILE\.ssh\uc_vps_ed25519 root@187.127.213.243 "umask 077; read -rs -p 'TypeSafe key: ' K; echo; set -f; IFS=; printf 'TYPESAFE_API_KEY=%s\n' `$K > /docker/uc-fixer/decide.env; chmod 600 /docker/uc-fixer/decide.env"
```
   - The command needs root's login shell on the box to be bash (`read -s` is a bash feature). Check once:
     `ssh -i $env:USERPROFILE\.ssh\uc_vps_ed25519 root@187.127.213.243 "getent passwd root"` must end in `/bin/bash`.
   - **Re-running this step rewrites `decide.env` from scratch and drops a `DECIDE_JEV_ENABLED=true` line.** To rotate
     the key while Jev is on, run it, then add the `DECIDE_JEV_ENABLED=true` line again (see "Switching Jev on"),
     then force-recreate the service.
3. The web image, because the `/jev` page is part of the dashboard bundle and the VPS web image predates it. It is
   built on the PC from the repo root (the owner's OK at that moment; it is the `:vps` tag, not the local
   `fixer-web`), then loaded on the box:
```powershell
( cd web; npm run build )
docker build -f Dockerfile.web -t ucmodelfixer-web:vps .
docker save ucmodelfixer-web:vps -o web.tar
scp -i $env:USERPROFILE\.ssh\uc_vps_ed25519 web.tar root@187.127.213.243:/docker/uc-fixer/
ssh -i $env:USERPROFILE\.ssh\uc_vps_ed25519 root@187.127.213.243 "docker load -i /docker/uc-fixer/web.tar && rm /docker/uc-fixer/web.tar"
```
   (`Dockerfile.web` copies `web/dist` and `preview` into an nginx image; the box's `nginx.conf` is mounted over the
   image's, see step 5.)
   **Note:** `Dockerfile.web` and the root `nginx.conf` it copies are UNTRACKED in the main checkout (not in git). The
   build uses those files as they exist on the owner's PC; committing them is a separate owner decision. Which
   `nginx.conf` the box uses: `deploy/vps/docker-compose.yml` mounts `./nginx.conf` (relative to `/docker/uc-fixer`)
   over `/etc/nginx/conf.d/default.conf`, and step 5 copies `deploy/vps/nginx.conf` of this branch there. So the box
   runs `deploy/vps/nginx.conf`, never the root one baked into the image.
4. The decide image, built on the PC from the repo root, then loaded on the box:
```powershell
docker build -f deploy/vps/decide/Dockerfile -t ucmodelfixer-decide:vps .
docker save ucmodelfixer-decide:vps -o decide.tar
scp -i $env:USERPROFILE\.ssh\uc_vps_ed25519 decide.tar root@187.127.213.243:/docker/uc-fixer/
ssh -i $env:USERPROFILE\.ssh\uc_vps_ed25519 root@187.127.213.243 "docker load -i /docker/uc-fixer/decide.tar && rm /docker/uc-fixer/decide.tar"
```
   (`docker save | ssh` through the PowerShell pipeline corrupts the binary stream, so the tar goes by `scp`.)
5. Copy the new `docker-compose.yml` and `nginx.conf` to `/docker/uc-fixer/`, then on the box, in this order:
   - `cd /docker/uc-fixer && docker compose up -d --force-recreate web` (starts the new web image, which also loads
     the new `nginx.conf`; no separate `nginx -s reload` is needed). nginx resolves `uc-fixer-decide` at request
     time, so it starts even while that container is absent (the decide routes answer 502 meanwhile), and it needs no
     reload after a later recreate of the decide container;
   - `docker compose up -d decide` (starts `uc-fixer-decide`, creates the schema `decide`).
6. Check: `curl -u gab https://uc-fixer.srv1866850.hstgr.cloud/api/decide/health` prompts for the password and
   should answer `{"ok":true,"jev_enabled":false,...}`.

The controller runs steps 3-6 only with the owner's explicit OK at that moment.

### On the PC after the deploy (the owner's `.env`, then two commands)
1. Set the service URL for the shell, and let the owner add the password line to the git-ignored repo-root `.env`
   himself (an agent never types it):
   - `UC_DECIDE_URL=https://uc-fixer.srv1866850.hstgr.cloud` (an environment variable, or `--url` on each command);
   - `UC_DECIDE_PASSWORD=<the uc-engine password>` as one line in `.env`.
2. Load the pilot answers as pending suggestions, first as a dry run (it builds the questions, prints the counts and
   sends nothing):
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
"$PY" -m engine.cli decide-import-pilot --source data/campus/source.json --materials data/campus/materials.json --pilot data/campus/jev_pilot.json --dry-run
"$PY" -m engine.cli decide-import-pilot --source data/campus/source.json --materials data/campus/materials.json --pilot data/campus/jev_pilot.json
```
3. Once the owner has confirmed answers on `/jev`, fetch them (writes `data/decide/confirmed/mat.category.json`):
```bash
"$PY" -m engine.cli decide-pull --type mat.category
```

### Post-deploy checks (spec section 8)
Against the real URL, in this order. Passwords are typed at the prompt (`curl -u name`), never on a command line:
1. Health: `curl -u gab https://uc-fixer.srv1866850.hstgr.cloud/api/decide/health` answers `ok: true`.
2. One `ask` as `uc-engine` (for example `decide-import-pilot` above, or a one-question POST to `/api/decide/ask`)
   answers 200 with an answer or `none / jev off`.
3. One review as the owner: open `/jev` as `gab`, accept one pending suggestion.
4. One confirmed fetch: `decide-pull --type mat.category` writes the file with that answer.
5. One refusal per role:
   - `uc-engine` on `/` (the dashboard) gives 403;
   - `uc-engine` on review (`POST /api/decide/review/<id>`) gives 403;
   - the owner (`gab`) on `ask` (`POST /api/decide/ask`) gives 403.

### Switching Jev on (later)
This is the owner's decision, for when the repair engine is ready, and each step needs the owner's OK at that moment.
Add the line `DECIDE_JEV_ENABLED=true` to `/docker/uc-fixer/decide.env` (append it; do not retype the key), then
`cd /docker/uc-fixer && docker compose up -d --force-recreate decide` (forced, so the new env file is certainly read).
The daily cap is
1,000,000 tokens (`DECIDE_DAILY_TOKEN_CAP`). The confidence of 0.8 (`DECIDE_MIN_CONFIDENCE`) is only a display
threshold, for the confidence bar and the "Accept all >=" default on `/jev`. Nothing is used by the engine until the
owner confirms it (source `owner`, or the files `decide-pull` writes).
To switch it off again, remove that line and recreate the same way.

### Rollback
`cd /docker/uc-fixer && docker compose rm -sf decide`. The `/api/decide/` locations then answer 502 and touch
nothing else (nginx resolves the upstream per request, so the dashboard keeps working). Taking the two locations out
of `nginx.conf` and reloading nginx stays optional but is recommended. The schema `decide` stays in the database,
with its answers, unless the owner asks for it to be dropped.

## Rollback
`cd /docker/uc-fixer && docker compose down -v`, then `rm -rf /docker/uc-fixer`. No other stack is touched.
