# Deploy Shurokkha to VPS 165.99.219.251

Copy-paste guide for this server, deploying from the GitHub repo
**https://github.com/mohammadyaksafu/DIU_Hackathon_final**. When finished, the app will be live at:

| What | URL |
|---|---|
| Web app | **https://165-99-219-251.sslip.io** |
| API docs | https://165-99-219-251.sslip.io/docs |
| Health check | https://165-99-219-251.sslip.io/health/ready |

`165-99-219-251.sslip.io` is a free hostname that always resolves to `165.99.219.251`, so you get real HTTPS without buying a domain. Have your own domain? See [Using your own domain](#using-your-own-domain) at the end.

How it runs: Docker on the VPS, with Caddy in front handling HTTPS and routing.

```
GitHub (private repo) ──git clone / git pull──► VPS 165.99.219.251
Internet ──443──► Caddy ──/api/*, /health/*, /docs──► api (FastAPI)
                        └─everything else───────────► web (Next.js)
                  api ──► Postgres + Redis
```

**Server requirements:** Ubuntu 22.04 or 24.04, 2 vCPU, 4 GB RAM (2 GB works with the swap from step 2), 20 GB disk.

**Time:** about 30 minutes. The first build takes 10–15 minutes because it trains the model.

> The commands assume you log in as `root`. If your provider gave you another user (e.g. `ubuntu`), replace `root` with it everywhere and keep the `sudo` in front of commands.

---

## Step 0: Push the deployment files to GitHub (on your PC, once)

The repo does not have the deployment files yet (`deploy/`, `docs/DEPLOY_VPS.md` and this guide). The server clones from GitHub, so push them first.

Your Desktop folder `DIU_Hackathon` has the same code as the repo but is not connected to git. These commands connect it without changing any of your files. Run them in **PowerShell on your PC**:

```powershell
cd "$HOME\Desktop\DIU_Hackathon"
git init -b main
git remote add origin https://github.com/mohammadyaksafu/DIU_Hackathon_final.git
git fetch origin
git reset origin/main
git branch --set-upstream-to=origin/main main
git status
```

`git status` should list **only** these as new (untracked):

```
DEPLOY_165.99.219.251.md
deploy/
docs/DEPLOY_VPS.md
```

Then commit and push them:

```powershell
git add deploy docs/DEPLOY_VPS.md DEPLOY_165.99.219.251.md
git commit -m "Add VPS deployment (Docker + Caddy)"
git push
```

If a GitHub sign-in window opens, sign in as `mohammadyaksafu`. Check the repo page in your browser: the `deploy` folder should now be there.

From now on this folder is a normal git clone: after changing code, run `git add`, `git commit` and `git push` here, then update the server ([Updating the app](#updating-the-app-after-code-changes)).

## Step 1: Connect to the server

In **PowerShell on your PC**:

```powershell
ssh root@165.99.219.251
```

> The format is `ssh USER@IP`, i.e. `ssh root@165.99.219.251`, **not** `ssh@root:165.99.219.251`.

Type `yes` if asked about the fingerprint, then enter the password your VPS provider gave you. Steps 2–7 run **on the server** (in this SSH window).

## Step 2: Prepare the server

```bash
# System updates + git
sudo apt update && sudo apt -y upgrade
sudo apt install -y git

# Firewall: allow only SSH, HTTP, HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw --force enable

# 2 GB swap so the build does not run out of memory
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

> If your VPS provider has a firewall in its web dashboard (often called "security group" or "cloud firewall"), open ports **80** and **443** there as well.

## Step 3: Install Docker

First check whether Docker is already installed:

```bash
docker --version && docker compose version
```

**If both print a version (e.g. `Docker version 29.1.3` and `Docker Compose version v5.5.1`), Docker is ready: go to step 4.** Otherwise install it:

```bash
curl -fsSL https://get.docker.com | sudo sh
docker --version && docker compose version
```

> If the installer warns that *"the docker command appears to already exist"*, press **Ctrl+C**: Docker is already there.

## Step 4: Give the server read access to the private repo

The repo is private, so the server needs its own key. A **deploy key** can only read this one repo: safer than putting your GitHub password or a personal token on the server.

**4a. Create a key on the server:**

```bash
ssh-keygen -t ed25519 -C "vps-165.99.219.251" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

Copy the whole line that starts with `ssh-ed25519`.

**4b. Add it to GitHub** (in your browser):

1. Open **https://github.com/mohammadyaksafu/DIU_Hackathon_final/settings/keys**
2. Click **Add deploy key**.
3. Title: `VPS 165.99.219.251`. Key: paste the line.
4. Leave **Allow write access unchecked** (the server only needs to read).
5. Click **Add key**.

**4c. Tell the server to use the key, then clone:**

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

Expected reply: `Hi mohammadyaksafu/DIU_Hackathon_final! You've successfully authenticated, but GitHub does not provide shell access.` (That message is a success.)

```bash
git clone git@github.com:mohammadyaksafu/DIU_Hackathon_final.git ~/shurokkha
ls ~/shurokkha/deploy      # should list: Caddyfile  docker-compose.prod.yml
```

If `ls` says `No such file or directory`, step 0 was not pushed yet. Push it, then run `cd ~/shurokkha && git pull`.

## Step 5: Create the settings file

This generates strong random passwords automatically. Run it as one block on the server:

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
cat .env
```

Then run `nano .env` and replace `you@example.com` with your real email (Let's Encrypt sends certificate notices there). Save with **Ctrl+O**, **Enter**, then exit with **Ctrl+X**.

Optional: to enable Gemini chat and AI-written case summaries, create an API key in Google AI Studio and set `GEMINI_API_KEY=` in the same file. Free-tier model access and quotas can change; without a key, the copilot uses deterministic fallbacks.

> `.env` holds your secrets. It stays only on the server: `.gitignore` keeps it out of git, so never copy it into the repo.

## Step 6: Build and start

```bash
cd ~/shurokkha/deploy
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

This takes 10–15 minutes the first time. Follow the progress:

```bash
docker compose -f docker-compose.prod.yml logs -f api caddy
```

It is ready when you see both:
- `startup complete` (from api)
- `certificate obtained successfully` (from caddy)

Press **Ctrl+C** to stop watching the logs; the app keeps running.

**Check it works:**

```bash
curl https://165-99-219-251.sslip.io/health/ready
docker compose -f docker-compose.prod.yml ps
```

The first command should print `"status":"ok"`, and every service should be `running` (api: `healthy`).

Now open **https://165-99-219-251.sslip.io** in your browser. The top-right badge should say **API ok**. Quick demo test:
1. **Customer app** → click *'You won a prize' scam* → press **পাঠান (Send)** → you should see a red Bangla card saying the transfer is paused (HOLD).
2. **Analyst console** → open the top alert → **Generate case summary**.

## Step 7: Lock down the Admin page (do this before sharing the link)

The site signs users in automatically, so the demo password is visible in the website's code. **Anyone with the link could open Admin and change the live risk policy.** To allow Admin only from your own internet connection:

1. On your PC, open **https://ifconfig.me** and note the IP shown (e.g. `103.12.34.56`).
2. On the server:

```bash
cd ~/shurokkha/deploy
# put your PC's IP here (several allowed, space-separated)
sed -i 's/^ADMIN_ALLOW_IPS=.*/ADMIN_ALLOW_IPS=103.12.34.56/' .env

# enable the admin block in the Caddyfile (removes the "# " in front of it)
sed -i '/# @adminblocked {/,/# }$/{s/^\t# \t/\t\t/;s/^\t# /\t/}' Caddyfile
sed -i '/# handle @adminblocked {/,/# }$/{s/^\t# \t/\t\t/;s/^\t# /\t/}' Caddyfile
grep -n -A7 "@adminblocked {" Caddyfile   # the block should now have no leading "#"

docker compose -f docker-compose.prod.yml --env-file .env up -d --force-recreate caddy
```

Check from your phone on mobile data (a different IP): `https://165-99-219-251.sslip.io/admin` should say **Admin is restricted**, while the other pages work normally.

> Your home or office IP can change. If Admin suddenly shows "restricted" for you, repeat this step with your new IP (only the first `sed` line and the last command are needed again).

---

## Updating the app after code changes

**On your PC** (PowerShell), push your changes:

```powershell
cd "$HOME\Desktop\DIU_Hackathon"
git add -A
git commit -m "Describe your change"
git push
```

**On the server:**

```bash
cd ~/shurokkha && git pull
cd deploy && docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Your `.env` is never touched by `git pull`. If `git pull` stops with *"Your local changes to … Caddyfile would be overwritten"* (because of step 7), run:

```bash
cd ~/shurokkha && git stash && git pull && git stash pop
```

## Everyday commands

Run these on the server from `~/shurokkha/deploy`. Create a shortcut first (add the same `alias` line to `~/.bashrc` to keep it):

```bash
cd ~/shurokkha/deploy
alias dc='docker compose -f docker-compose.prod.yml --env-file .env'
```

| Task | Command |
|---|---|
| Status | `dc ps` |
| Live logs | `dc logs -f api` (or `web`, `caddy`, `postgres`) |
| Restart | `dc restart` |
| Stop (data kept) | `dc down` |
| Start again | `dc up -d` |
| Back up the database | `dc exec -T postgres pg_dump -U shurokkha shurokkha > ~/backup_$(date +%F).sql` |
| Restore a backup | `cat ~/backup_2026-10-02.sql \| dc exec -T postgres psql -U shurokkha shurokkha` |
| Reset demo data (deletes all alerts and labels) | `dc down -v && dc up -d` |
| Free disk space | `docker image prune -f && docker builder prune -f` |

The app restarts automatically after a crash or a server reboot.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ssh: connect ... timed out` | Wrong IP, the server is off, or the provider's firewall blocks port 22. Check the VPS dashboard. |
| `ssh: Could not resolve hostname root:165...` | Wrong format. Use `ssh root@165.99.219.251`. |
| Step 0: `git push` is rejected (`fetch first` / `non-fast-forward`) | Someone pushed to the repo meanwhile. Run `git pull --rebase`, then `git push`. |
| Step 4: `Permission denied (publickey)` | The deploy key was not added, or was pasted incompletely. Repeat 4a–4b, then `ssh -T git@github.com` again. |
| Step 4: `Repository not found` | Same cause as above: for a private repo, GitHub says "not found" when the key has no access. |
| Browser certificate error, or Caddy logs `challenge failed` | Ports 80/443 are blocked. Check `sudo ufw status` and the provider dashboard firewall, then `dc restart caddy`. |
| Caddy logs `rateLimited` / `too many certificates` | Let's Encrypt limits certificates for shared hostnames like sslip.io. Wait an hour and `dc restart caddy`, or set `DOMAIN=165.99.219.251.nip.io` in `.env` and run `dc up -d --build` (the web app must be rebuilt for a new domain). |
| Build ends with `Killed` or `exit code 137` | Out of memory. Make sure the swap from step 2 is on (`free -h` shows Swap 2.0G), then run the build again. |
| Page loads but the badge says **API offline** | The web image was built for a different domain. Run `dc up -d --build web`. |
| `502 Bad Gateway` right after start | The API is still booting. Wait 30–60 s and check `dc logs api`. |
| Case summary says "Rule-based summary (AI unavailable)" | No Gemini key or quota is available. Add `GEMINI_API_KEY` to `.env`, then `dc up -d api`; check AI Studio for current quotas. |
| Forgot the demo password | `grep DEMO_PASSWORD ~/shurokkha/deploy/.env` (you rarely need it: the website signs in automatically). |

## Using your own domain

1. At your DNS provider, add an **A record**: name `shurokkha` (or `@`), value `165.99.219.251`.
2. Wait until `nslookup shurokkha.yourdomain.com` returns `165.99.219.251`.
3. On the server, edit `.env`: `DOMAIN=shurokkha.yourdomain.com`.
4. Rebuild (the web app stores the API address at build time):

```bash
cd ~/shurokkha/deploy && docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

## Good to know

- Only ports 22, 80 and 443 are open. Postgres, Redis, the API and the web app are reachable only inside Docker.
- `/metrics` is blocked from the internet. From the server: `dc exec api curl -s localhost:8000/metrics`.
- The API runs as a single worker on purpose (live state is held in memory). Do not add `--workers`.
- All data is synthetic. The model is rebuilt identically (seed 42) on every build.
