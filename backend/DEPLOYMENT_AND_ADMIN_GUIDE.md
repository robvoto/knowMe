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
/usr/local/bin/deploy-knowme
/usr/local/bin/knowme-status
```

## Normal AWS update

Preferred update command:

```bash
use-ubuntu
```

Then:

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
