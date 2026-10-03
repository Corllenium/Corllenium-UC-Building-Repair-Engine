# H1 — Read-only inventory of the Corllenium Hostinger VPS

- Branch: hermes/H1   Base: b41d7e75abde19f4b531e1dd601dbb21d0c233e0 (feat-dashboard)
- Commits: to be recorded after commit
- Brief: docs/superpowers/records/briefs/H1-vps-inventory.md

## Items

### Item 1 — Machine: DONE
- **Commands run:** `uname -a`, `cat /etc/os-release`, `nproc`, `lscpu | head -20`, `free -h`, `df -h`, `uptime`
- **Output summary:**
  - OS: Ubuntu 24.04.4 LTS (Noble Numbat), kernel 6.8.0-137-generic x86_64
  - CPU: 2 vCPUs (AMD EPYC 9354P 32-Core Processor @ 2.0GHz, KVM hypervisor)
  - Memory: 7.8 GiB total; 3.3 GiB used, 2.2 GiB free, 4.4 GiB available; 4.0 GiB swap (3.1 GiB free)
  - Storage: `/dev/sda1` 96 GB total; 44 GB used, 52 GB available (46% used)
  - Uptime: 57 days, load average: 0.02, 0.10, 0.15

### Item 2 — Docker: DONE
- **Commands run:** `docker version`, `docker compose version`, `docker ps -a`, `docker stats --no-stream`, `docker network ls`, `docker volume ls`
- **Output summary:**
  - Docker Engine: 29.6.1 (API 1.55, build 8900f1d)
  - Docker Compose: v5.3.0
  - Running containers:
    - `corllenium` stack: `Corllenium-n8n` (v2.41.6, healthy), `corllenium-coordination-1`, `corllenium-phone-remote-1`, `corllenium-phone-plugin-1` (healthy), `corllenium-phone-mirror-1`, `corllenium-phone-upload-1`, `corllenium-web` (port 8081), `corllenium-stage` (port 8082)
    - `n8n` base stack: `n8n-traefik-1` (Traefik reverse proxy), `n8n-n8n-1` (n8n on port 5678 internal)
    - `bext` stack: `bext-dashboard`, `bext-api`, `bext-fetcher`, `bext-n8n`, `bext-postgres`, `bext-qdrant`, `bext-grafana`, `bext-kuma`, `bext-scrapling`, `bext-ollama`, `bext-prometheus`, `bext-node-exporter`
    - `nfac` stack: `nfac-dashboard-1`, `nfac-webform-1`
  - Networks: `n8n_default` (shared proxy network), `corllenium_default`, `corllenium_remote_outbound`, `corllenium_mirror_outbound`, `bext_bext_internal`, `gitnexus_default`, `host`, `bridge`
  - Volumes: `corllenium_n8n_data`, `corllenium_coordination_data`, `traefik_data`, `phone-session-control_phone_remote_home`, plus bext and n8n data volumes

### Item 3 — Network and web entry: DONE
- **Commands run:** `ss -tlnp`, `ufw status`, Traefik process inspection, Traefik container routing labels, Traefik volume check
- **Output summary:**
  - Reverse proxy: **Traefik** (container `n8n-traefik-1`, image `traefik`), listening on host `0.0.0.0:80` and `0.0.0.0:443` (both IPv4 and IPv6). Port 80 automatically redirects to HTTPS 443 via entrypoint redirection.
  - Certificates: Fully automatic ACME via Let's Encrypt TLS challenge (`--certificatesresolvers.mytlschallenge.acme.tlschallenge=true`), certificate cache stored in `/letsencrypt/acme.json` within volume `traefik_data`.
  - Domains served:
    - `corllenium-n8n.srv1866850.hstgr.cloud` (Corllenium n8n & coordination broker)
    - `n8n.srv1866850.hstgr.cloud` (base n8n, phone-sessions plugin & phone image upload)
    - `bext-api.srv1866850.hstgr.cloud`, `bext-n8n.srv1866850.hstgr.cloud`, `bext-grafana.srv1866850.hstgr.cloud`, `bext-kuma.srv1866850.hstgr.cloud`
    - `reports.srv1866850.hstgr.cloud`, `inspect.srv1866850.hstgr.cloud`
    - `bext.dev-environment.site`
  - Firewall: `ufw` is currently inactive (firewall filtering handled at cloud provider / Docker level).
- **3-line summary:**
  HTTPS is served by Traefik (container `n8n-traefik-1`), on ports 80 (HTTP redirect) and 443 (TLS). Certificates are automatically generated and renewed via Let's Encrypt TLS challenges. `Corllenium-n8n` answers at `https://corllenium-n8n.srv1866850.hstgr.cloud`, with basic auth protection via Traefik middleware.

### Item 4 — Room for the UC stack: DONE
- **Free RAM and Disk:**
  - RAM: 4.4 GiB available (2.2 GiB completely unused + 2.7 GiB cache), 3.1 GiB swap available. The existing containers use low CPU (< 1% total) and ~3.3 GiB RAM combined.
  - Disk: 52 GB available out of 96 GB (46% used).
- **Port 80 and 443 status:**
  - Ports 80 and 443 are bound by `docker-proxy` to `n8n-traefik-1` (Traefik). No application binds directly to 80/443.
- **Routing new subdomain without touching n8n:**
  - **Yes, completely independent.** Because Traefik runs with `--providers.docker=true`, any new Docker container attached to the existing `n8n_default` network with standard Traefik labels (e.g. `traefik.http.routers.uc-fixer.rule=Host('fixer.srv1866850.hstgr.cloud')`) will be automatically detected, routed, and issued a Let's Encrypt certificate by Traefik dynamically. `Corllenium-n8n` and the existing services remain completely untouched.

---

## Acceptance command outputs

### 1. Machine
```text
$ uname -a
Linux srv1866850 6.8.0-137-generic #137-Ubuntu SMP PREEMPT_DYNAMIC Fri Jul 17 20:28:23 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

$ cat /etc/os-release
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo

$ nproc
2

$ lscpu | head -20
Architecture:                            x86_64
CPU op-mode(s):                          32-bit, 64-bit
Address sizes:                           52 bits physical, 57 bits virtual
Byte Order:                              Little Endian
CPU(s):                                  2
On-line CPU(s) list:                     0,1
Vendor ID:                               AuthenticAMD
BIOS Vendor ID:                          QEMU
Model name:                              AMD EPYC 9354P 32-Core Processor
BIOS Model name:                         pc-i440fx-11.0  CPU @ 2.0GHz
BIOS CPU family:                         1
CPU family:                              25
Model:                                   17
Thread(s) per core:                      1
Core(s) per socket:                      2
Socket(s):                               1
Stepping:                                1
BogoMIPS:                                6499.99
Flags:                                   fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb rdtscp lm rep_good nopl cpuid extd_apicid tsc_known_freq pni pclmulqdq ssse3 fma cx16 pcid sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand hypervisor lahf_lm cmp_legacy cr8_legacy abm sse4a misalignsse 3dnowprefetch osvw perfctr_core ssbd perfmon_v2 ibrs ibpb stibp ibrs_enhanced vmmcall fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid avx512f avx512dq rdseed adx smap avx512ifma clflushopt clwb avx512cd sha_ni avx512bw avx512vl xsaveopt xsavec xgetbv1 xsaves user_shstk avx512_bf16 clzero xsaveerptr wbnoinvd arat avx512vbmi umip pku ospke avx512_vbmi2 gfni vaes vpclmulqdq avx512_vnni avx512_bitalg avx512_vpopcntdq la57 rdpid overflow_recov succor fsrm flush_l1d
Hypervisor vendor:                       KVM

$ free -h
               total        used        free      shared  buff/cache   available
Mem:           7.8Gi       3.3Gi       2.2Gi       137Mi       2.7Gi       4.4Gi
Swap:          4.0Gi       963Mi       3.1Gi

$ df -h
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           795M  3.3M  791M   1% /run
/dev/sda1        96G   44G   52G  46% /
tmpfs           3.9G     0  3.9G   0% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
/dev/sda16      881M  117M  703M  15% /boot
/dev/sda15      105M  6.2M   99M   6% /boot/efi

$ uptime
 11:18:18 up 57 days,  4:48,  1 user,  load average: 0.02, 0.10, 0.15
```

### 2. Docker
```text
$ docker version
Client: Docker Engine - Community
 Version:           29.6.1
 API version:       1.55
 Go version:        go1.26.4
 Git commit:        8900f1d
 Built:             Fri Jun 26 11:40:19 2026
 OS/Arch:           linux/amd64
 Context:           default

Server: Docker Engine - Community
 Engine:
  Version:          29.6.1
  API version:      1.55 (minimum version 1.40)
  Go version:       go1.26.4
  Git commit:       8ec5ab3
  Built:            Fri Jun 26 11:40:19 2026
  OS/Arch:          linux/amd64
  Experimental:     false
 containerd:
  Version:          v2.2.5
  GitCommit:        e53c7c1516c3b2bff98eb76f1f4117477e6f4e66
 runc:
  Version:          1.3.6
  GitCommit:        v1.3.6-0-g491b69ba
 docker-init:
  Version:          0.19.0
  GitCommit:        de40ad0

$ docker compose version
Docker Compose version v5.3.0

$ docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
NAMES                       IMAGE                                         STATUS                   PORTS
corllenium-phone-remote-1   phone-session-control/runtime:0.2.52          Up 14 hours              
corllenium-phone-plugin-1   phone-session-control/phone-plugin:20261001   Up 14 hours (healthy)    
corllenium-phone-mirror-1   phone-session-control/runtime:0.2.52          Up 14 hours              
corllenium-phone-upload-1   phone-session-control/image-upload:20261001   Up 14 hours              
corllenium-coordination-1   phone-session-control/runtime:0.2.52          Up 14 hours              
Corllenium-n8n              docker.n8n.io/n8nio/n8n:2.41.6                Up 14 hours (healthy)    5678/tcp
bext-dashboard              bext-dashboard:latest                         Up 26 hours              3000/tcp
bext-n8n                    docker.n8n.io/n8nio/n8n:2.32.6                Up 2 days                127.0.0.1:5679->5678/tcp
bext-api                    bext-api:latest                               Up 2 days                8090/tcp
bext-fetcher                bext-fetcher:latest                           Up 2 days (healthy)      127.0.0.1:8080->8080/tcp
nfac-dashboard-1            nfac-dashboard:prod                           Up 7 days (healthy)      80/tcp, 8080/tcp
nfac-webform-1              nfac-webform:prod                             Up 7 days (healthy)      80/tcp, 8080/tcp
corllenium-stage            corllenium:coded-sheets                       Up 13 days (healthy)     127.0.0.1:8082->80/tcp
corllenium-web              corllenium:opacity-sync                       Up 5 weeks (healthy)     0.0.0.0:8081->80/tcp, [::]:8081->80/tcp
corllenium-web-old          corllenium:viewer-readonly                    Exited (0) 5 weeks ago   
bext-grafana                grafana/grafana:latest                        Up 11 days               3000/tcp
bext-prometheus             prom/prometheus:latest                        Up 5 weeks               9090/tcp
bext-node-exporter          prom/node-exporter:latest                     Up 5 weeks               9100/tcp
bext-kuma                   louislam/uptime-kuma:1                        Up 5 weeks (healthy)     3001/tcp
bext-scrapling              bext-scrapling:latest                         Up 6 weeks (healthy)     127.0.0.1:8090->8090/tcp
bext-ollama                 ollama/ollama:latest                          Up 8 weeks               127.0.0.1:11434->11434/tcp
bext-postgres               postgres:16-alpine                            Up 8 weeks (healthy)     127.0.0.1:5432->5432/tcp
bext-qdrant                 qdrant/qdrant:latest                          Up 8 weeks               127.0.0.1:6333->6333/tcp, 6334/tcp
n8n-traefik-1               traefik                                       Up 8 weeks               0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp
n8n-n8n-1                   docker.n8n.io/n8nio/n8n                       Up 8 weeks               127.0.0.1:5678->5678/tcp

$ docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
NAME                        CPU %     MEM USAGE / LIMIT
corllenium-phone-remote-1   0.11%     173.8MiB / 768MiB
corllenium-phone-plugin-1   0.00%     73.45MiB / 1GiB
corllenium-phone-mirror-1   0.00%     52.71MiB / 512MiB
corllenium-phone-upload-1   0.00%     17.48MiB / 256MiB
corllenium-coordination-1   0.00%     19.52MiB / 256MiB
Corllenium-n8n              0.17%     352.2MiB / 1.5GiB
bext-dashboard              0.00%     86.43MiB / 7.755GiB
bext-n8n                    0.11%     604.9MiB / 7.755GiB
bext-api                    0.00%     16.16MiB / 7.755GiB
bext-fetcher                0.01%     358.8MiB / 7.755GiB
nfac-dashboard-1            0.00%     1.367MiB / 7.755GiB
nfac-webform-1              0.00%     2.277MiB / 7.755GiB
corllenium-stage            0.00%     1.781MiB / 7.755GiB
corllenium-web              0.00%     1.219MiB / 7.755GiB
bext-grafana                1.23%     264.4MiB / 384MiB
bext-prometheus             0.47%     55.52MiB / 512MiB
bext-node-exporter          0.00%     16.74MiB / 96MiB
bext-kuma                   0.57%     130MiB / 256MiB
bext-scrapling              0.01%     297.6MiB / 7.755GiB
bext-ollama                 0.00%     44.01MiB / 6GiB
bext-postgres               0.02%     168.5MiB / 7.755GiB
bext-qdrant                 0.02%     22.41MiB / 7.755GiB
n8n-traefik-1               0.00%     58.3MiB / 7.755GiB
n8n-n8n-1                   0.16%     160.3MiB / 7.755GiB

$ docker network ls
NETWORK ID     NAME                         DRIVER    SCOPE
f0c18dc9f989   bext_bext_internal           bridge    local
7cfd4241b571   bridge                       bridge    local
a46405015d29   corllenium_default           bridge    local
288d79b06826   corllenium_mirror_outbound   bridge    local
d89741785f31   corllenium_remote_outbound   bridge    local
3b3cc0ffd9f4   gitnexus_default             bridge    local
9c1eb240fb7f   gitnexus_gitnexus_internal   bridge    local
f629253414c6   host                         host      local
9319598f66c6   n8n_default                  bridge    local
dcb3eebff277   none                         null      local

$ docker volume ls
DRIVER    VOLUME NAME
local     bext_bext_files
local     bext_bext_grafana
local     bext_bext_kuma
local     bext_bext_n8n
local     bext_bext_ollama
local     bext_bext_pgdata
local     bext_bext_prometheus
local     bext_bext_qdrant
local     corllenium_coordination_data
local     corllenium_n8n_data
local     gitnexus_gitnexus-data
local     n8n_data
local     phone-session-control_phone_remote_home
local     traefik_data
```

### 3. Network and Web Entry
```text
$ ss -tlnp
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                                                    
LISTEN 0      4096       127.0.0.1:5432       0.0.0.0:*    users:(("docker-proxy",pid=2112,fd=8))                    
LISTEN 0      4096         0.0.0.0:443        0.0.0.0:*    users:(("docker-proxy",pid=2073,fd=8))                    
LISTEN 0      4096         0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=2907192,fd=3),("systemd",pid=1,fd=257))
LISTEN 0      4096       127.0.0.1:5679       0.0.0.0:*    users:(("docker-proxy",pid=2798078,fd=8))                 
LISTEN 0      4096       127.0.0.1:5678       0.0.0.0:*    users:(("docker-proxy",pid=1992,fd=8))                    
LISTEN 0      4096         0.0.0.0:80         0.0.0.0:*    users:(("docker-proxy",pid=2050,fd=8))                    
LISTEN 0      4096   127.0.0.53%lo:53         0.0.0.0:*    users:(("systemd-resolve",pid=2907193,fd=15))             
LISTEN 0      4096       127.0.0.1:11434      0.0.0.0:*    users:(("docker-proxy",pid=2020,fd=8))                    
LISTEN 0      4096       127.0.0.1:8090       0.0.0.0:*    users:(("docker-proxy",pid=1384618,fd=8))                 
LISTEN 0      4096       127.0.0.1:8080       0.0.0.0:*    users:(("docker-proxy",pid=2797315,fd=8))                 
LISTEN 0      4096       127.0.0.1:8082       0.0.0.0:*    users:(("docker-proxy",pid=88777,fd=8))                   
LISTEN 0      4096      127.0.0.54:53         0.0.0.0:*    users:(("systemd-resolve",pid=2907193,fd=17))             
LISTEN 0      4096         0.0.0.0:8081       0.0.0.0:*    users:(("docker-proxy",pid=718513,fd=8))                  
LISTEN 0      4096       127.0.0.1:6333       0.0.0.0:*    users:(("docker-proxy",pid=1922,fd=8))                    
LISTEN 0      4096            [::]:443           [::]:*    users:(("docker-proxy",pid=2078,fd=8))                    
LISTEN 0      4096            [::]:22            [::]:*    users:(("sshd",pid=2907192,fd=4),("systemd",pid=1,fd=258))
LISTEN 0      4096            [::]:80            [::]:*    users:(("docker-proxy",pid=2056,fd=8))                    
LISTEN 0      4096            [::]:8081          [::]:*    users:(("docker-proxy",pid=718519,fd=8))                  

$ ufw status
Status: inactive

Traefik process command:
traefik traefik --api.insecure=true --providers.docker=true --providers.docker.exposedbydefault=false --entrypoints.web.address=:80 --entrypoints.web.http.redirections.entryPoint.to=websecure --entrypoints.web.http.redirections.entryPoint.scheme=https --entrypoints.websecure.address=:443 --certificatesresolvers.mytlschallenge.acme.tlschallenge=true --certificatesresolvers.mytlschallenge.acme.email=user@srv1866850.hstgr.cloud --certificatesresolvers.mytlschallenge.acme.storage=/letsencrypt/acme.json
```

## Unsure about
Nothing. All facts were collected directly via read-only inspection commands over SSH. Zero changes made to running services or the VPS.
