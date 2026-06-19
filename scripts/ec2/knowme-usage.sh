#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/var/lib/knowme/data/questions.log"
COUNT="${1:-20}"
TIMEZONE="Australia/Sydney"

if [ ! -f "$LOG_FILE" ]; then
  echo "No KnowMe question log found at: $LOG_FILE"
  exit 0
fi

echo "== Recent KnowMe questions =="
echo "Time zone: Sydney"
echo "Log: $LOG_FILE"
echo

tail -n "$COUNT" "$LOG_FILE" | python3 -c '
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

UNKNOWN = {"", "-", "unknown"}
TZ = ZoneInfo("Australia/Sydney")

def value(parts, key):
    prefix = key + "="
    for part in parts:
        if part.startswith(prefix):
            return part.split("=", 1)[1].strip()
    return "-"

def nice_time(raw):
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M Sydney")
    except Exception:
        return raw

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    parts = [p.strip() for p in line.split(" | ")]
    ts = nice_time(parts[0]) if parts else "-"
    source = value(parts, "source_page")
    name = value(parts, "name")
    company = value(parts, "company")
    ip_hash = value(parts, "client_ip_hash")
    question = value(parts, "q")

    who_parts = []
    if name.lower() not in UNKNOWN:
        who_parts.append(name)
    if company.lower() not in UNKNOWN:
        who_parts.append(company)
    who = " / ".join(who_parts) if who_parts else "anonymous"

    print(f"{ts} | {source:<8} | {who:<24} | ip={ip_hash:<16} | {question}")
'

echo
printf "Total questions logged: "
wc -l < "$LOG_FILE" | tr -d ' '
