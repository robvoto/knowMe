# KnowMe Deployment and Admin Guide

## Purpose

KnowMe is a FastAPI CV Q&A application for recruiter-style questions about a candidate.

This document describes the production deployment on AWS EC2.

## Production architecture

KnowMe runs as a separate application on the same EC2 host as Job Hunter.

Shared infrastructure:

```text
EC2 host
Public IP
Nginx
systemd
Let's Encrypt / Certbot
```

KnowMe-specific runtime:

```text
Public URL:          https://knowme.robvoto.com
Application path:    /home/ubuntu/knowme
Backend path:        /home/ubuntu/knowme/backend
Python venv:         /home/ubuntu/knowme/.venv
Environment file:    /etc/knowme/knowme.env
Persistent data:     /var/lib/knowme/data
Repo data symlink:   /home/ubuntu/knowme/backend/data -> /var/lib/knowme/data
systemd service:     knowme.service
Internal bind:       127.0.0.1:8001
Nginx site file:     /etc/nginx/sites-available/knowme
```

Job Hunter remains separate:

```text
Public URL:          https://jobhunter.robvoto.com/start
systemd service:     job-hunter.service
Internal bind:       127.0.0.1:8765
```

Do not reuse Job Hunter routes, auth, UI, environment files, ports, data folders, or service names for KnowMe.

## Application structure

```text
backend/app/main.py          FastAPI application entry point
backend/app/config.py        Filesystem paths and runtime constants
backend/static/index.html    Public recruiter-facing page
backend/static/admin.html    Admin page
backend/data/                Local/default data files
backend/requirements.txt     Python dependencies
```

Runtime entry point from `/home/ubuntu/knowme/backend`:

```bash
/home/ubuntu/knowme/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

## Required environment variables

Production secrets are stored only in:

```text
/etc/knowme/knowme.env
```

Required:

```env
ADMIN_PASSWORD=<strong-admin-password>
ADMIN_COOKIE_SECRET=<long-random-secret>
```

Optional but used in production:

```env
OPENAI_API_KEY=<server-side-openai-key>
ANALYTICS_SALT=<random-salt-for-hashed-analytics>
LLM_DAILY_TOKEN_CAP=50000
```

Do not commit secrets, `.env` files, API keys, or admin passwords to GitHub.

## Data persistence

KnowMe reads and writes through `backend/data`.

On AWS, `backend/data` is a symlink:

```text
/home/ubuntu/knowme/backend/data -> /var/lib/knowme/data
```

Persistent files include:

```text
cv.txt
star.txt
prompt_defaults.json
prompt_config.json
questions.log
question_events.jsonl
answer_cache.json
llm_usage.json
```

## Fresh AWS install

Run on the EC2 host as the app owner.

Session Manager may log in as `ssm-user`. Switch to `ubuntu` first:

```bash
use-ubuntu
```

If the helper is unavailable:

```bash
sudo -iu ubuntu
```

`use-ubuntu` opens a new shell as `ubuntu`. If pasting multiple commands, run `use-ubuntu` by itself first, then run the remaining commands after the prompt shows the `ubuntu` user.

### 1. Check base platform

```bash
hostname
lsb_release -a
python3 --version
nginx -v
systemctl status nginx --no-pager
sudo ss -tlnp | grep -E ':80|:443|:8765|:8001'
```

Expected baseline:

```text
Ubuntu 24.04
Python 3.12.x
Nginx active
No public FastAPI port exposed
```

### 2. Configure GitHub deploy key

Create the EC2 deploy key:

```bash
ssh-keygen -t ed25519 -C "knowme-ec2-readonly" -f ~/.ssh/knowme_deploy_key
cat ~/.ssh/knowme_deploy_key.pub
```

Add the public key to:

```text
GitHub -> robvoto/knowMe -> Settings -> Deploy keys
```

Keep write access disabled.

Verify access:

```bash
ssh -vT -i ~/.ssh/knowme_deploy_key -o IdentitiesOnly=yes git@github.com 2>&1 | grep -E "Offering public key|Server accepts key|Permission denied|Authenticated"
```

Expected:

```text
Server accepts key
Authenticated to github.com
```

### 3. Clone KnowMe

```bash
cd /home/ubuntu
GIT_SSH_COMMAND='ssh -i ~/.ssh/knowme_deploy_key -o IdentitiesOnly=yes' \
  git clone git@github.com:robvoto/knowMe.git knowme
```

Verify:

```bash
cd /home/ubuntu/knowme
ls -la
ls -la backend
cat backend/requirements.txt
```

### 4. Create Python environment

```bash
cd /home/ubuntu/knowme
python3 -m venv .venv
source .venv/bin/activate
python --version
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
```

Verify:

```bash
/home/ubuntu/knowme/.venv/bin/python -c "import fastapi, uvicorn, openai, dotenv; print('KnowMe deps OK')"
```

Expected:

```text
KnowMe deps OK
```

### 5. Create persistent data path

```bash
sudo mkdir -p /var/lib/knowme/data
sudo chown -R ubuntu:ubuntu /var/lib/knowme

if [ -z "$(ls -A /var/lib/knowme/data 2>/dev/null)" ]; then
  cp -a /home/ubuntu/knowme/backend/data/. /var/lib/knowme/data/
fi

cd /home/ubuntu/knowme/backend

if [ -d data ] && [ ! -L data ]; then
  mv data data.repo-backup.$(date +%Y%m%d%H%M%S)
fi

ln -sfn /var/lib/knowme/data /home/ubuntu/knowme/backend/data
```

Verify:

```bash
ls -la /home/ubuntu/knowme/backend/data
ls -la /var/lib/knowme/data
```

Expected:

```text
/home/ubuntu/knowme/backend/data -> /var/lib/knowme/data
```

### 6. Create production environment file

```bash
sudo mkdir -p /etc/knowme
sudo nano /etc/knowme/knowme.env
```

Required shape:

```env
OPENAI_API_KEY=<server-side-openai-key>
ANALYTICS_SALT=<random-salt-for-hashed-analytics>
ADMIN_PASSWORD=<strong-admin-password>
ADMIN_COOKIE_SECRET=<long-random-secret>
LLM_DAILY_TOKEN_CAP=50000
```

Secure the file:

```bash
sudo chown root:ubuntu /etc/knowme/knowme.env
sudo chmod 640 /etc/knowme/knowme.env
```

Verify variable names without exposing values:

```bash
sudo grep -E '^(ADMIN_PASSWORD|ADMIN_COOKIE_SECRET|OPENAI_API_KEY|ANALYTICS_SALT|LLM_DAILY_TOKEN_CAP)=' /etc/knowme/knowme.env | sed 's/=.*/=***/'
```

### 7. Create systemd service

```bash
sudo nano /etc/systemd/system/knowme.service
```

Service file:

```ini
[Unit]
Description=KnowMe FastAPI App
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/knowme/backend
EnvironmentFile=/etc/knowme/knowme.env
ExecStart=/home/ubuntu/knowme/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable knowme
sudo systemctl start knowme
```

Verify:

```bash
sudo systemctl status knowme --no-pager
curl http://127.0.0.1:8001/health
sudo ss -tlnp | grep 8001
```

Expected:

```text
Active: active (running)
{"ok":true}
127.0.0.1:8001
```

Do not expose port `8001` in the AWS security group.

### 8. Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/knowme
```

Nginx site:

```nginx
server {
    listen 80;
    server_name knowme.robvoto.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 120;
        proxy_connect_timeout 30;
        proxy_send_timeout 120;
    }
}
```

Enable:

```bash
sudo ln -sfn /etc/nginx/sites-available/knowme /etc/nginx/sites-enabled/knowme
sudo nginx -t
sudo systemctl reload nginx
```

Verify HTTP routing:

```bash
curl -I -H "Host: knowme.robvoto.com" http://127.0.0.1/
curl https://knowme.robvoto.com/health
curl -I https://jobhunter.robvoto.com/start
```

### 9. Enable HTTPS

Only run Certbot after the service and HTTP route work.

```bash
sudo certbot --nginx -d knowme.robvoto.com
```

Choose redirect to HTTPS when prompted.

Verify certificate and routes:

```bash
curl -Iv https://knowme.robvoto.com/ 2>&1 | grep -E "subject:|issuer:|SSL certificate verify|HTTP/"
curl https://knowme.robvoto.com/health
curl -I https://jobhunter.robvoto.com/start
sudo ss -tlnp | grep -E ':8001|:8765'
sudo systemctl status knowme --no-pager
sudo systemctl status job-hunter --no-pager
```

Expected:

```text
subject: CN=knowme.robvoto.com
SSL certificate verify ok
{"ok":true}
127.0.0.1:8001
127.0.0.1:8765
```

## Install EC2 helper commands

KnowMe includes EC2 helper scripts under:

```text
scripts/ec2/
```

Install or refresh helper commands on EC2.

First switch to the app owner if needed:

```bash
use-ubuntu
```

Then run:

```bash
cd /home/ubuntu/knowme
sudo bash scripts/ec2/install-helpers.sh
```

Installed commands:

```text
/usr/local/bin/knowme
/usr/local/bin/deploy-knowme
/usr/local/bin/knowme-status
/usr/local/bin/knowme-usage
```

Preferred simple command:

```bash
knowme deploy        # pull code, install dependencies, restart, health check
knowme refresh       # restart KnowMe only
knowme status        # service status and health check
knowme logs          # recent questions in Sydney time
knowme logs 50       # last 50 questions in Sydney time
```

## Usage logs

Raw question log:

```bash
tail -n 50 /var/lib/knowme/data/questions.log
```

Readable recent usage in Sydney time:

```bash
knowme-usage
```

Show more rows:

```bash
knowme-usage 50
```

Live raw log while testing:

```bash
tail -f /var/lib/knowme/data/questions.log
```

Stop live view with `Ctrl+C`.

## Normal AWS update

Preferred update command:

```bash
use-ubuntu
```

Then:

```bash
knowme deploy
```

Legacy helper equivalent:

```bash
deploy-knowme
```

Manual update equivalent:

```bash
use-ubuntu
```

Then:

```bash
cd /home/ubuntu/knowme
GIT_SSH_COMMAND='ssh -i ~/.ssh/knowme_deploy_key -o IdentitiesOnly=yes' git pull --ff-only
source .venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart knowme
sudo systemctl status knowme --no-pager
curl https://knowme.robvoto.com/health
```

## Diagnostics

Check service:

```bash
sudo systemctl status knowme --no-pager
sudo journalctl -u knowme -n 100 --no-pager
```

Check ports:

```bash
sudo ss -tlnp | grep -E ':8001|:8765|:80|:443'
```

Check Nginx routing:

```bash
sudo nginx -T | grep -nE 'server_name|default_server|proxy_pass|ssl_certificate|knowme|jobhunter'
sudo nginx -t
```

Check local app:

```bash
curl http://127.0.0.1:8001/health
```

Check public app:

```bash
curl https://knowme.robvoto.com/health
curl -I https://jobhunter.robvoto.com/start
```

## Common failures

### `knowme.robvoto.com` shows Job Hunter

The HTTPS request is falling through to the Job Hunter SSL server block.

Fix by ensuring KnowMe has its own Nginx server block and certificate:

```bash
sudo nginx -T | grep -nE 'server_name|proxy_pass|ssl_certificate|knowme|jobhunter'
sudo certbot --nginx -d knowme.robvoto.com
```

### `ADMIN_PASSWORD is required`

Check the env file and service configuration:

```bash
sudo systemctl cat knowme
sudo grep '^ADMIN_PASSWORD=' /etc/knowme/knowme.env | sed 's/=.*/=***/'
```

### `ADMIN_COOKIE_SECRET is required`

Check:

```bash
sudo grep '^ADMIN_COOKIE_SECRET=' /etc/knowme/knowme.env | sed 's/=.*/=***/'
```

### Missing data files

Check the symlink and persistent data:

```bash
ls -la /home/ubuntu/knowme/backend/data
ls -la /var/lib/knowme/data
```

### `knowme-usage: command not found`

The helper installer on EC2 is stale or the latest helper was not installed.

Immediate fix:

```bash
cd /home/ubuntu/knowme
sudo install -m 755 scripts/ec2/knowme-usage.sh /usr/local/bin/knowme-usage
knowme-usage
```

Normal fix after pulling latest code:

```bash
cd /home/ubuntu/knowme
sudo bash scripts/ec2/install-helpers.sh
knowme logs
```

### Admin analytics sections show `None`

This means the backend version is old or the analytics code has not been deployed.

Deploy latest code:

```bash
knowme deploy
```

Expected admin analytics after usage exists:

```text
Top canonical questions populated
Top normalized questions populated
Intent distribution populated
Recent recruiter questions populated
```

### `curl -I` returns 405

Some KnowMe endpoints allow `GET` but not `HEAD`. Use normal `curl` for health checks:

```bash
curl https://knowme.robvoto.com/health
```

## Do not do

Do not:

```text
Expose port 8001 publicly
Store secrets in GitHub
Run Certbot before KnowMe service and HTTP routing work
Change Job Hunter service while deploying KnowMe
Route unknown hostnames to Job Hunter
Use robvoto.com as the KnowMe route
Use AWS CloudShell as proof of EC2 runtime state
Treat local VS Code state as proof of AWS runtime state
```

## Local development

From the repo root on Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/admin
```

## Security hardening prior to reactivation (19 October 2026)

KnowMe remains subject to normal deployment review; this code change does not deploy AWS or restore DNS. Administrator login now sets a **Secure, HttpOnly, SameSite=Strict** cookie that browsers send only over HTTPS, with a fresh random signed token and an enforced 8-hour server-side expiry. Older fixed-value admin cookies are invalid; log in again. Failed administrator logins are throttled after five failures per observed network peer over 15 minutes (process-local limiter). Ensure HTTPS/proxy routing is correctly configured before production use.

Public paid-LLM request cooldown identity no longer trusts caller-supplied `client_id` or `session_id`; it uses a server-derived, secret-salted peer hash even if optional analytics hashing is disabled. This reduces trivial identity-rotation abuse, but is not a substitute for an external/proxy rate limiter, atomic daily budget reservations or a billing hard cap; those remain prerequisites for confidently opening a paid API to the internet. Consider proxy/peer trust carefully when deploying behind a reverse proxy. Code regression tests added for cookie uniqueness/expiry, failed-login throttling and non-user-controlled rate identity; the local test runner reported 21 tests passing.

### Paid-API concurrency guard (19 October 2026)

Public AI requests now acquire a non-blocking, **per-process one-request semaphore** before the rate-limit check and upstream OpenAI call. Concurrent requests receive HTTP 429 with `Retry-After: 10`, and the semaphore is released even if the provider fails. HTTP 503 responses no longer disclose provider exception text to visitors. Two regression tests verify contention handling and release after an error; the complete local suite passed **23 tests with exit code 0**.

This guard is **not** a global billing hard cap: additional Uvicorn workers/instances each have their own semaphore, and the persisted token total is not an atomic reservation. Before public internet redeployment, verify one-worker operation or add a shared atomic budget store, enforce upstream spending caps and reverse-proxy rate limits, and validate the full deployment security posture. These changes did not reactivate AWS or DNS.

### Cross-origin admin logout protection (19 October 2026)

The admin logout endpoint rejects an explicitly supplied `Origin` that does not match the application base URL and clears the HTTPS-only, HttpOnly, SameSite=Strict session cookie. Verify that the public reverse proxy preserves the canonical HTTPS host/scheme so same-origin logout works in the deployed environment. Tests cover blocked cross-site logout and successful same-origin logout; all 25 local tests passed (exit code 0). This does not replace the remaining public-relaunch proxy and shared-spend checks.

### Spending ledger corruption protection (19 October 2026)

The paid-LLM usage ledger now fails closed when existing JSON is unreadable or malformed, rather than resetting to zero and permitting further paid requests. Writes stage a unique temporary file and replace the ledger atomically to reduce torn-file corruption. An absent ledger remains valid for first launch. Regression tests cover corrupted JSON and successful atomic replacement; 27 local tests passed with exit code 0. This does **not** solve cross-process spending reservations: KnowMe issue #4 remains open until a shared atomic budget is implemented and concurrency-tested.

### Local developer launch exposure (19 October 2026)

Running `python -m backend.app.main` now binds only to `127.0.0.1:8000` with Uvicorn auto-reload disabled. This prevents the development entry point from accidentally opening KnowMe to the LAN or Internet. Production deployment uses its separately configured service and proxy; verify its network binding independently before restoring DNS. A regression test covers this configuration; the full local suite passed 28 tests (exit code 0).

### Shared transactional spending-budget foundation (19 October 2026)

`backend/app/llm_budget_store.py` implements an **independent, not-yet-connected** SQLite transaction store. `reserve()` uses an immediate transaction so simultaneous workers cannot reserve more than the declared token limit; `settle()` is idempotent, releases unused reservations, and charges unexpected excess usage rather than hiding it. Unsettled reservations remain reserved after a crash/restart (conservative fail-closed behaviour). Connections are explicitly closed to prevent Windows database file locks. Four regression tests cover concurrency, duplicate settlement, restart persistence and excess usage; the full local suite passed 32 tests with exit code 0.

**Do not mark public spending protection complete yet.** The existing `main.py` call path still uses JSON usage accounting. Issue #4 requires wiring the transactional reservation into that path, determining a safe worst-case token estimate, reconciling or migrating existing JSON totals without resetting the prior spent budget, and testing multi-process handling and provider timeout/error cases. Until then, do not restore public service solely on the strength of this module.
