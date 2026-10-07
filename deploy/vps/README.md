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

## Rollback
`cd /docker/uc-fixer && docker compose down -v`, then `rm -rf /docker/uc-fixer`. No other stack is touched.
