#!/usr/bin/env bash
#
# Build binary tunggal Linux dengan alamat server ditanam di dalamnya.
# Pakai : ./build-linux.sh [URL-SERVER]
# Contoh: ./build-linux.sh http://192.168.11.126:8000
#
set -euo pipefail
cd "$(dirname "$0")"

SERVER="${1:-${PANEL_SERVER_URL:-}}"
if [[ -z "$SERVER" ]]; then
  echo "Pakai: $0 <URL-SERVER>   contoh: $0 http://192.168.11.126:8000"
  exit 1
fi

printf 'SERVER = "%s"\n' "$SERVER" > _build_config.py
python3 -m PyInstaller --onefile --hidden-import=_build_config --name panel-agent panel_agent.py \
  || pyinstaller --onefile --name panel-agent panel_agent.py
echo
echo "Selesai: dist/panel-agent  (cukup 1 file ini + klik di PC Linux mana pun)"
