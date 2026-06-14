#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/knowme"
VENV_DIR="$APP_DIR/.venv"
ENV_FILE="/etc/knowme/knowme.env"
SERVICE_NAME="knowme"
DEPLOY_KEY="/home/ubuntu/.ssh/knowme_deploy_key"
HEALTH_URL="https://knowme.robvoto.com/health"
LOCAL_HEALTH_URL="http://127.0.0.1:8001/health"

echo "== KnowMe deploy =="

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu. Use: use-ubuntu" >&2
  exit 1
fi

if [ ! -d "$APP_DIR/.git" ]; then
  echo "ERROR: $APP_DIR is not a Git checkout." >&2
  exit 1
fi

if [ ! -f "$DEPLOY_KEY" ]; then
  echo "ERROR: missing deploy key: $DEPLOY_KEY" >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: missing env file: $ENV_FILE" >&2
  exit 1
fi

cd "$APP_DIR"

echo "-- Git status before pull --"
git status --short

echo "-- Pull latest code --"
GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes" git pull --ff-only

echo "-- Install dependencies --"
source "$VENV_DIR/bin/activate"
pip install -r backend/requirements.txt

echo "-- Restart service --"
sudo systemctl restart "$SERVICE_NAME"
sleep 3

echo "-- Service status --"
sudo systemctl status "$SERVICE_NAME" --no-pager

echo "-- Recent logs --"
sudo journalctl -u "$SERVICE_NAME" -n 60 --no-pager

echo "-- Health checks --"
curl -fsS "$LOCAL_HEALTH_URL"
echo
curl -fsS "$HEALTH_URL"
echo

echo "== KnowMe deploy complete =="
