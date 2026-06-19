#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/usr/local/bin"

install_helper() {
  local source_file="$1"
  local command_name="$2"

  if [ ! -f "$SCRIPT_DIR/$source_file" ]; then
    echo "ERROR: missing $SCRIPT_DIR/$source_file" >&2
    exit 1
  fi

  sudo install -m 755 "$SCRIPT_DIR/$source_file" "$TARGET_DIR/$command_name"
  echo "Installed $TARGET_DIR/$command_name"
}

install_helper "knowme.sh" "knowme"
install_helper "deploy-knowme.sh" "deploy-knowme"
install_helper "knowme-status.sh" "knowme-status"
install_helper "knowme-usage.sh" "knowme-usage"

echo "KnowMe EC2 helpers installed."
echo "Use: knowme deploy"
echo "Use: knowme refresh"
echo "Use: knowme status"
echo "Use: knowme logs [count]"
echo "Use: deploy-knowme"
echo "Use: knowme-status"
echo "Use: knowme-usage [count]"
