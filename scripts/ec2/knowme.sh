#!/usr/bin/env bash
set -euo pipefail

APP="/home/ubuntu/knowme"
KEY="/home/ubuntu/.ssh/knowme_deploy_key"
SERVICE="knowme"
HEALTH="https://knowme.robvoto.com/health"
LOCAL_HEALTH="http://127.0.0.1:8001/health"
LOG="/var/lib/knowme/data/questions.log"

case "${1:-}" in
  deploy)
    cd "$APP"
    echo "Pulling latest KnowMe code..."
    GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" git pull --ff-only

    echo "Installing dependencies..."
    source "$APP/.venv/bin/activate"
    pip install -r backend/requirements.txt

    echo "Restarting KnowMe..."
    sudo systemctl restart "$SERVICE"
    sleep 2

    echo "Checking health..."
    curl -fsS "$LOCAL_HEALTH"
    echo
    curl -fsS "$HEALTH"
    echo
    ;;

  refresh|restart)
    echo "Restarting KnowMe..."
    sudo systemctl restart "$SERVICE"
    sleep 2
    curl -fsS "$LOCAL_HEALTH"
    echo
    curl -fsS "$HEALTH"
    echo
    ;;

  status)
    sudo systemctl status "$SERVICE" --no-pager
    echo
    echo "Local health:"
    curl -fsS "$LOCAL_HEALTH"
    echo
    echo "Public health:"
    curl -fsS "$HEALTH"
    echo
    ;;

  logs|usage)
    if command -v knowme-usage >/dev/null 2>&1; then
      knowme-usage "${2:-20}"
      exit 0
    fi
    if [ ! -f "$LOG" ]; then
      echo "No log found: $LOG"
      exit 0
    fi
    tail -n "${2:-20}" "$LOG"
    ;;

  *)
    echo "Usage:"
    echo "  knowme deploy        Pull code, install deps, restart, health check"
    echo "  knowme refresh       Restart KnowMe and health check"
    echo "  knowme status        Show service and health"
    echo "  knowme logs [count]  Show recent questions in Sydney time"
    exit 1
    ;;
esac
