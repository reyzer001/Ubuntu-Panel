#!/usr/bin/env bash
#
# Ubuntu Panel — Cloudflare Quick Tunnel launcher
# Menjalankan cloudflared quick tunnel ke frontend (port 3000).
#
# Pakai: ./tunnel.sh {start|stop|status|help}
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/ubuntu-panel"
TUNNEL_PID_FILE="$STATE_DIR/tunnel.pid"
TUNNEL_LOG="$STATE_DIR/tunnel.log"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

c_info() { printf '\033[1;34m[tunnel]\033[0m %s\n' "$*"; }
c_ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
c_warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
c_err()  { printf '\033[1;31m[err ]\033[0m %s\n' "$*" >&2; }

alive() {
  local pid
  [[ -f "$TUNNEL_PID_FILE" ]] || return 1
  pid="$(cat "$TUNNEL_PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  ps -p "$pid" -o uid= >/dev/null 2>&1
}

wait_for_url() {
  local log="$1" timeout=15 elapsed=0
  while (( elapsed < timeout )); do
    if grep -qoP 'https://[a-z0-9-]+\.trycloudflare\.com' "$log" 2>/dev/null; then
      grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$log" | tail -1
      return 0
    fi
    sleep 1
    (( elapsed++ ))
  done
  return 1
}

do_start() {
  if alive; then
    local url=""
    url="$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | tail -1 || true)"
    c_warn "Tunnel sudah jalan (PID $(cat "$TUNNEL_PID_FILE"))"
    [[ -n "$url" ]] && c_ok "URL: $url"
    return 0
  fi

  if ! command -v cloudflared &>/dev/null; then
    c_err "cloudflared tidak ditemukan."
    return 1
  fi

  mkdir -p "$STATE_DIR"
  : > "$TUNNEL_LOG"

  c_info "Memulai Cloudflare Quick Tunnel ke port ${FRONTEND_PORT}…"
  setsid cloudflared tunnel --url "http://localhost:${FRONTEND_PORT}" \
    >> "$TUNNEL_LOG" 2>&1 &
  local pid=$!
  disown "$pid" 2>/dev/null || true
  echo "$pid" > "$TUNNEL_PID_FILE"

  local url
  if url="$(wait_for_url "$TUNNEL_LOG")"; then
    c_ok "Tunnel berjalan (PID $pid)"
    c_ok "URL: $url"
    c_info "Log: $TUNNEL_LOG"
  else
    if alive; then
      c_warn "Tunnel berjalan (PID $pid), menunggu URL…"
      c_info "Cek log: tail -f $TUNNEL_LOG"
    else
      c_err "Tunnel gagal dimulai. Cek log: $TUNNEL_LOG"
      return 1
    fi
  fi
}

do_stop() {
  if ! alive; then
    c_warn "Tunnel tidak berjalan"
    rm -f "$TUNNEL_PID_FILE"
    return 0
  fi
  local pid
  pid="$(cat "$TUNNEL_PID_FILE")"
  c_info "Menghentikan tunnel (PID $pid)…"
  kill "$pid" 2>/dev/null || true
  sleep 1
  if alive; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$TUNNEL_PID_FILE"
  c_ok "Tunnel dihentikan"
}

do_status() {
  if alive; then
    local pid url
    pid="$(cat "$TUNNEL_PID_FILE")"
    url="$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | tail -1 || true)"
    c_ok "Tunnel berjalan (PID $pid)"
    [[ -n "$url" ]] && c_ok "URL: $url"
  else
    c_warn "Tunnel tidak berjalan"
  fi
}

case "${1:-help}" in
  start)  do_start  ;;
  stop)   do_stop   ;;
  status) do_status ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    echo ""
    echo "  start   - Mulai Cloudflare Quick Tunnel"
    echo "  stop    - Hentikan tunnel"
    echo "  status  - Cek status tunnel"
    ;;
esac
