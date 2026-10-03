# Brief H1 — read-only inventory of the Corllenium Hostinger VPS

Rules: [`AGENTS.md`](../../../../AGENTS.md). This job is **read-only on the VPS**.

## Goal
The owner wants the UC MODEL FIXER dashboard (web + FastAPI API + Postgres 16, now Docker containers on the
owner's PC) hosted on the Corllenium Hostinger VPS, next to the n8n already running there. Before anything
is designed or installed, collect the exact facts of that VPS. Claude writes the hosting design from this
report.

## Files
- Create: `docs/superpowers/records/hermes/H1-report.md` (this job's report) in your worktree, on branch
  `hermes/H1`, made from `feat-dashboard`.
- Nothing else. No change on the VPS.

## Items

### Item 1 — Machine
- **Run:** `uname -a`, `cat /etc/os-release`, `nproc`, `lscpu | head -20`, `free -h`, `df -h`,
  `uptime`.
- **Done when:** the report shows each command and its real output.

### Item 2 — Docker
- **Run:**
  - `docker version`, `docker compose version`;
  - `docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'`;
  - `docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'`;
  - `docker network ls`, `docker volume ls`.
- **Do NOT** print container environment variables or inspect output that contains secrets.
- **Done when:** the outputs are in the report.

### Item 3 — Network and web entry
- **Run:**
  - `sudo ss -tlnp` (or `ss -tln` without sudo);
  - which reverse proxy serves HTTPS (nginx, Caddy, Traefik, or n8n's own; as a process or container);
  - the domain or domains that point at this VPS (the n8n address included);
  - how certificates are made (Let's Encrypt? which tool);
  - `sudo ufw status` (or the firewall in use).
- **Done when:** the outputs plus a 3-line summary are in the report: "HTTPS is served by …, on ports …;
  n8n answers at …".

### Item 4 — Room for the UC stack
- **Write in the report:**
  - the free RAM and disk after what already runs;
  - whether ports 80 and 443 are taken, and by what;
  - whether a new subdomain could be routed to a new container without touching n8n.
- **Done when:** these answers are in the report, each backed by an output above.

## Acceptance commands
The commands in Items 1-3, run on the VPS, with their real output pasted. Redact any secret (tokens,
passwords, keys) before pasting.

## Rules for this job
- **Read-only.** Never install, restart, stop, upgrade or reconfigure anything; never edit a file on the
  VPS.
- n8n must not be disturbed.
- Never paste a secret into the report or the chat.

## Report
`docs/superpowers/records/hermes/H1-report.md`, format `docs/superpowers/records/hermes/README.md`. Commit
it on `hermes/H1`, then `tools/jobs.py done H1 --branch hermes/H1`.
