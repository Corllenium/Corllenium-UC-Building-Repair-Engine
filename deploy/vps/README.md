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
ssh -t -i $env:USERPROFILE\.ssh\uc_vps_ed25519 root@187.127.213.243 "umask 077; read -rs -p 'TypeSafe key: ' K; echo; printf 'TYPESAFE_API_KEY=%s\n' `$K > /docker/uc-fixer/decide.env; chmod 600 /docker/uc-fixer/decide.env"
```
3. The image, built on the PC from the repo root, then loaded on the box:
```powershell
docker build -f deploy/vps/decide/Dockerfile -t ucmodelfixer-decide:vps .
docker save ucmodelfixer-decide:vps -o decide.tar
scp -i $env:USERPROFILE\.ssh\uc_vps_ed25519 decide.tar root@187.127.213.243:/docker/uc-fixer/
ssh -i $env:USERPROFILE\.ssh\uc_vps_ed25519 root@187.127.213.243 "docker load -i /docker/uc-fixer/decide.tar && rm /docker/uc-fixer/decide.tar"
```
   (`docker save | ssh` through the PowerShell pipeline corrupts the binary stream, so the tar goes by `scp`.)
4. Copy the new `docker-compose.yml` and `nginx.conf` to `/docker/uc-fixer/`, then on the box, in this order:
   - `cd /docker/uc-fixer && docker compose up -d decide` (starts `uc-fixer-decide`, creates the schema `decide`);
   - `docker exec uc-fixer-web nginx -s reload` (the route needs the decide container to exist first; reload again
     after any recreate of `uc-fixer-decide`, because nginx keeps the address it resolved).
5. Check: `curl -u gab https://uc-fixer.srv1866850.hstgr.cloud/api/decide/health` prompts for the password and
   should answer `{"ok":true,"jev_enabled":false,...}`.

### Switching Jev on (later)
This is the owner's decision, for when the repair engine is ready, and each step needs the owner's OK at that moment.
Add the line `DECIDE_JEV_ENABLED=true` to `/docker/uc-fixer/decide.env` (append it; do not retype the key), then
`cd /docker/uc-fixer && docker compose up -d --force-recreate decide` (forced, so the new env file is certainly read).
Then reload nginx as in step 4. The daily cap is
1,000,000 tokens (`DECIDE_DAILY_TOKEN_CAP`); a minimum confidence of 0.8 gates what is accepted without review.
To switch it off again, remove that line and recreate the same way.

### Rollback
`cd /docker/uc-fixer && docker compose rm -sf decide`. Then take the `/api/decide/` locations out of `nginx.conf` and
reload nginx (or leave them: they answer 502 while the service is down and touch nothing else). The schema `decide`
stays in the database, with its answers, unless the owner asks for it to be dropped.

## Rollback
`cd /docker/uc-fixer && docker compose down -v`, then `rm -rf /docker/uc-fixer`. No other stack is touched.
