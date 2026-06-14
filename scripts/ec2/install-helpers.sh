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

install_helper "deploy-knowme.sh" "deploy-knowme"
install_helper "knowme-status.sh" "knowme-status"

echo "KnowMe EC2 helpers installed."
echo "Use: deploy-knowme"
echo "Use: knowme-status"
