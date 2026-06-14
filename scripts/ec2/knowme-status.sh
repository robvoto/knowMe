#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="knowme"
LOCAL_HEALTH_URL="http://127.0.0.1:8001/health"
PUBLIC_HEALTH_URL="https://knowme.robvoto.com/health"
JOBHUNTER_URL="https://jobhunter.robvoto.com/start"

echo "== KnowMe status =="

echo "-- Service --"
sudo systemctl status "$SERVICE_NAME" --no-pager || true

echo "-- Recent logs --"
sudo journalctl -u "$SERVICE_NAME" -n 80 --no-pager || true

echo "-- Ports --"
sudo ss -tlnp | grep -E ':8001|:8765|:80|:443' || true

echo "-- Local health --"
curl -fsS "$LOCAL_HEALTH_URL" || true
echo

echo "-- Public KnowMe health --"
curl -fsS "$PUBLIC_HEALTH_URL" || true
echo

echo "-- Job Hunter safety check --"
curl -I "$JOBHUNTER_URL" || true

echo "-- Nginx route summary --"
sudo nginx -T 2>/dev/null | grep -nE 'server_name|proxy_pass|ssl_certificate|knowme|jobhunter' || true

echo "== End KnowMe status =="
