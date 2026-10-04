# Deploying Shurokkha on a VPS

One server runs everything in Docker. Caddy sits in front and gets a free HTTPS certificate automatically.

```
Internet ──443──► Caddy ──/api/*, /health/*, /docs──► api (FastAPI, port 8000)
                        └─everything else───────────► web (Next.js, port 3000)
                  api ──► Postgres (alerts, audit log) + Redis (cache)
```

The web app and API share one domain, so there is no CORS setup and only ports 80/443 are open.

Files used: `deploy/docker-compose.prod.yml`, `deploy/Caddyfile`, `deploy/.env.example`.

The code reaches the server through the GitHub repo **https://github.com/mohammadyaksafu/DIU_Hackathon_final**: you push from your PC, the server pulls with a read-only deploy key.

```
Your PC ──git push──► GitHub (private) ──git clone / git pull──► VPS ──docker compose──► live site
```

> Step-by-step version with the IP `165.99.219.251` already filled in: [`DEPLOY_165.99.219.251.md`](../DEPLOY_165.99.219.251.md).

---

## 0. What you need

| Item | Minimum |
|---|---|
| VPS | Ubuntu 22.04 or 24.04, **2 vCPU, 4 GB RAM** (2 GB works with the swap from step 2), 20 GB disk |
| Domain | A domain or subdomain you control, e.g. `shurokkha.yourdomain.com`. No domain? See the tip below. |
| Access | SSH as root or a sudo user, e.g. `ssh root@165.99.219.251` (format is `ssh USER@IP`) |
| GitHub | Admin access to the repo (to push and to add a deploy key) |

> **No domain?** Use `sslip.io`, which maps a name to your IP for free. If your VPS IP is `203.0.113.7`, set `DOMAIN=203-0-113-7.sslip.io`. HTTPS still works and you can skip step 1.

The first build trains the model inside the API image (about 3–5 minutes of CPU). Budget 10–15 minutes for the first deploy.

To enable the AI chat and generated case summaries, set `GEMINI_API_KEY` in `deploy/.env` using a key from [Google AI Studio](https://aistudio.google.com/apikey). Keep it on the server; never add it to frontend variables. Gemini free-tier access and quotas depend on current model/account availability. Without a key, SOP lookup still uses its deterministic retrieval fallback.

## 1. Point your domain at the VPS

At your DNS provider, add an **A record**:

| Type | Name | Value |
|---|---|---|
| A | `shurokkha` (or `@` for the root domain) | your VPS public IPv4 |

Check it from your own computer. It must print the VPS IP before you continue, or HTTPS will fail:

```bash
nslookup shurokkha.yourdomain.com
```

## 2. Prepare the server

SSH in, then run:

```bash
# Updates + git
sudo apt update && sudo apt -y upgrade
sudo apt install -y git

# Firewall: SSH + HTTP + HTTPS only
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw --force enable

# 2 GB swap (prevents the build from running out of memory on small VPSes)
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

> Some VPS providers also have a firewall in their web dashboard (security groups). Open 80 and 443 there too.

> After `apt upgrade`, a screen may list services to restart (`needrestart`). That is normal; the defaults are fine.

## 3. Install Docker

First check whether Docker is already there (many VPS images include it):

```bash
docker --version && docker compose version
```

**If both print a version, skip to step 4.** Otherwise install it:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # only needed if you are not root
# if not root: log out and SSH back in so the group change applies
docker --version && docker compose version
```

> If the installer warns that *"the docker command appears to already exist"*, press **Ctrl+C**: Docker is already installed and nothing else is needed.

## 4. Get the code onto the server from GitHub

### 4a. Push the deployment files (on your PC, once)

The server can only deploy what is in the repo, so `deploy/` and these docs must be pushed first.

If your project folder is **not yet connected to git** (it was copied or downloaded), connect it without changing any files. In PowerShell:

```powershell
cd "$HOME\Desktop\DIU_Hackathon"
git init -b main
git remote add origin https://github.com/mohammadyaksafu/DIU_Hackathon_final.git
git fetch origin
git reset origin/main
git branch --set-upstream-to=origin/main main
git status            # should list only the new deploy files as untracked
```

Then commit and push (sign in as the repo owner if a GitHub window opens):

```powershell
git add deploy docs/DEPLOY_VPS.md DEPLOY_165.99.219.251.md
git commit -m "Add VPS deployment (Docker + Caddy)"
git push
```

Check on GitHub that the `deploy` folder is now in the repo.

### 4b. Give the server read access (deploy key)

The repo is private, so the server needs a key. A **deploy key** can only read this one repo: safer than putting your GitHub password or a personal token on the server.

On the server:

```bash
ssh-keygen -t ed25519 -C "vps-deploy" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

Copy the whole line starting with `ssh-ed25519`. In your browser:

1. Open **https://github.com/mohammadyaksafu/DIU_Hackathon_final/settings/keys**.
2. **Add deploy key**. Title: `VPS`. Key: paste the line.
3. Leave **Allow write access** unchecked.
4. **Add key**.

Back on the server, tell SSH to use that key for GitHub and test it:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null
ssh -T git@github.com
```

Expected: `Hi mohammadyaksafu/DIU_Hackathon_final! You've successfully authenticated, but GitHub does not provide shell access.` (this is the success message).

### 4c. Clone

```bash
git clone git@github.com:mohammadyaksafu/DIU_Hackathon_final.git ~/shurokkha
ls ~/shurokkha/deploy      # Caddyfile  docker-compose.prod.yml
```

If `deploy` is missing, step 4a was not pushed yet: push it, then `cd ~/shurokkha && git pull`.

## 5. Configure secrets

```bash
cd ~/shurokkha/deploy
cp .env.example .env
nano .env
```

Fill in:

| Variable | Value |
|---|---|
| `DOMAIN` | `shurokkha.yourdomain.com` (no `https://`, no trailing slash) |
| `ACME_EMAIL` | your email (Let's Encrypt expiry notices) |
| `POSTGRES_PASSWORD` | output of `openssl rand -hex 32` |
| `JWT_SECRET` | output of another `openssl rand -hex 32` |
| `DEMO_PASSWORD` | any password for the demo users |
| `GEMINI_API_KEY` | optional: key from Google AI Studio for AI chat and summaries (free quota may vary) |
| `GEMINI_MODEL` | optional: Gemini model id; default `gemini-3.8-flash` |
| `LLM_PROVIDER` | optional: default `auto`, which prefers Gemini when its key is set |

```bash
chmod 600 .env
```

**Shortcut:** this creates `.env` with random secrets in one go (replace the domain and email):

```bash
cd ~/shurokkha/deploy
cat > .env <<EOF
DOMAIN=165-99-219-251.sslip.io
ACME_EMAIL=you@example.com
POSTGRES_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
DEMO_PASSWORD=$(openssl rand -hex 8)
LLM_PROVIDER=auto
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
ANTHROPIC_API_KEY=
ADMIN_ALLOW_IPS=127.0.0.1
EOF
chmod 600 .env
```

> `.env` holds your secrets and lives only on the server. `.gitignore` keeps it out of git; never commit it.

## 6. Build and start

```bash
cd ~/shurokkha/deploy
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Watch progress (Ctrl+C stops watching; the containers keep running):

```bash
docker compose -f docker-compose.prod.yml logs -f api caddy
```

You are done when the API logs `startup complete` and Caddy logs `certificate obtained successfully`.

**Verify:**

```bash
curl https://shurokkha.yourdomain.com/health/ready     # "status":"ok"
docker compose -f docker-compose.prod.yml ps           # all services "running" / api "healthy"
```

Then open `https://shurokkha.yourdomain.com` in a browser. The top-right badge should say **API ok**. Run the demo: Customer app → a scam scenario → Send; Analyst console → open the alert.

API docs are at `https://shurokkha.yourdomain.com/docs`.

## 7. Lock down the Admin page (recommended)

The site signs users in automatically, so `DEMO_PASSWORD` is built into the public JavaScript. **Anyone who opens the site can reach the Admin page and change the live policy.** For a public demo, allow Admin only from your own IP:

1. Find your IP: open https://ifconfig.me from your own computer.
2. In `deploy/.env` set `ADMIN_ALLOW_IPS=YOUR.IP.ADDRESS` (several are fine, space-separated, CIDR allowed).
3. In `deploy/Caddyfile`, uncomment the `@adminblocked` block (remove the leading `# `).
4. Apply:

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --force-recreate caddy
```

Other visitors now get `403 Admin is restricted` on `/admin` and the admin API. The rest of the site is unaffected.

## 8. Updating after code changes

**On your PC**, push the change:

```powershell
cd "$HOME\Desktop\DIU_Hackathon"
git add -A
git commit -m "Describe your change"
git push
```

**On the server**, pull and rebuild:

```bash
cd ~/shurokkha && git pull
cd deploy && docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

`git pull` never touches `.env`. If it stops with *"Your local changes to … Caddyfile would be overwritten"* (because of step 7), keep your edit while pulling:

```bash
cd ~/shurokkha && git stash && git pull && git stash pop
```

## 9. Day-to-day operations

All commands run from `~/shurokkha/deploy`. To save typing:

```bash
alias dc='docker compose -f docker-compose.prod.yml --env-file .env'
```

| Task | Command |
|---|---|
| Status | `dc ps` |
| Logs | `dc logs -f api` (or `web`, `caddy`, `postgres`) |
| Restart everything | `dc restart` |
| Stop | `dc down` (data is kept) |
| Deploy new code | `cd ~/shurokkha && git pull && cd deploy && dc up -d --build` (step 8) |
| Back up the database | `dc exec -T postgres pg_dump -U shurokkha shurokkha > backup_$(date +%F).sql` |
| Restore a backup | `cat backup.sql \| dc exec -T postgres psql -U shurokkha shurokkha` |
| Reset demo data (deletes all alerts and labels) | `dc down -v && dc up -d` |
| Free disk after many rebuilds | `docker image prune -f && docker builder prune -f` |

Containers restart automatically after a crash or a server reboot (`restart: unless-stopped`).

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ssh: Could not resolve hostname root:…` | Wrong format. Use `ssh root@165.99.219.251` (`USER@IP`). |
| `git push` rejected (`fetch first` / `non-fast-forward`) | The repo has newer commits. Run `git pull --rebase`, then `git push`. |
| `Permission denied (publickey)` on the server | Deploy key missing or pasted incompletely. Repeat step 4b, then `ssh -T git@github.com`. |
| `Repository not found` when cloning | Same cause: for a private repo, GitHub answers "not found" when the key has no access. |
| `deploy/` folder missing after clone | Step 4a was not pushed. Push it, then `git pull` on the server. |
| Browser shows a certificate error, or Caddy logs `challenge failed` | DNS does not point at the VPS yet, or port 80/443 is blocked (check `ufw status` and the provider's dashboard firewall). Fix it, then `dc restart caddy`. |
| Build stops with `Killed` or `exit code 137` | Out of memory. Add the swap from step 2, or use a 4 GB VPS. |
| Site loads but the badge says **API offline** | The web image was built with a different `DOMAIN`. The API address is fixed at build time, so after changing `DOMAIN`, rebuild: `dc up -d --build web`. |
| `502 Bad Gateway` right after starting | The API is still booting. Wait about 30 s and check `dc logs api`. |
| Copilot shows "Rule-based summary (AI unavailable)" | Add `GEMINI_API_KEY` from Google AI Studio to `.env`, then run `dc up -d api`. Check the model's free-tier quota in AI Studio. |
| `429 Too Many Requests` | Rate limit (default 1200 requests/min per client IP). Raise it by adding `RATE_LIMIT_PER_MINUTE` under `api.environment` in the compose file. |

## Notes

- The API runs as a single worker on purpose: the live feature state is held in memory (see README, "Scaling"). Do not add `--workers`.
- The model and synthetic data are baked into the API image at build time (seed 42), so every rebuild produces the same model.
- `/metrics` (Prometheus) is blocked from the internet by Caddy. From the server, use `dc exec api curl -s localhost:8000/metrics`.
