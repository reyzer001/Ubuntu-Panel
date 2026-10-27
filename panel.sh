#!/usr/bin/env bash
#
# Ubuntu Panel — launcher
# Menjalankan backend (FastAPI) + frontend (Next.js) dari luar folder keduanya.
#
# Pakai : ./panel.sh {start|stop|restart|status|logs [backend|frontend]|help}
# Env   : BACKEND_PORT=8000  FRONTEND_PORT=3000  DEV=1 (mode development)
#
# Contoh:
#   ./panel.sh start                 # jalankan semua (mode produksi)
#   DEV=1 ./panel.sh start           # jalankan dengan hot-reload
#   FRONTEND_PORT=3001 ./panel.sh start
#   ./panel.sh logs backend          # ikuti log backend

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
RUN="$ROOT/.run"
LOGS="$RUN/logs"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
DEV_MODE="${DEV:-0}"

BACKEND_PID_FILE="$RUN/backend.pid"
FRONTEND_PID_FILE="$RUN/frontend.pid"
BACKEND_PORT_FILE="$RUN/backend.port"
FRONTEND_PORT_FILE="$RUN/frontend.port"
SELF="$ROOT/panel.sh"
TARGET_USER="${SUDO_USER:-$(id -un)}"

# Utamakan Node.js LTS dari /usr/bin (v18) agar kompatibel dengan Next.js 14,
# menghindari konflik dengan versi Node eksperimental (v26) di ~/.local/bin
export PATH="/usr/bin:/bin:$PATH"

# ----------------------------------------------------------------- hak akses
am_root() { [[ "$(id -u)" == "0" ]]; }

# sudo bisa dipakai? (non-interaktif, atau interaktif bila ada TTY)
can_sudo() {
  sudo -n true 2>/dev/null && return 0
  [[ -t 0 ]]
}

# Sisa `sudo ./panel.sh start` membuat .run/, log, stamp, dan build
# frontend milik root — start berikutnya sebagai user biasa GAGAL menulis.
# Ambil alih kepemilikan otomatis (sudo chown) sebelum apa pun ditulis.
reclaim_runtime_files() {
  local targets=("$RUN")
  local f bad
  for f in "$BACKEND/.venv" "$FRONTEND/node_modules" \
           "$FRONTEND/.next" "$FRONTEND/.env.local"; do
    [[ -e "$f" ]] && targets+=("$f")
  done
  bad="$(find "${targets[@]}" -user root -print -quit 2>/dev/null || true)"
  [[ -z "$bad" ]] && return 0

  c_warn "Artefak milik 'root' ditemukan (${bad}) — ambil alih kepemilikan…"
  if sudo -n chown -R "${TARGET_USER}:" "${targets[@]}" 2>/dev/null; then
    c_ok "Kepemilikan dikembalikan ke ${TARGET_USER}"
  elif [[ -t 0 ]]; then
    sudo -p "[sudo] password ${TARGET_USER}: " \
      chown -R "${TARGET_USER}:" "${targets[@]}" &&
      c_ok "Kepemilikan dikembalikan ke ${TARGET_USER}" ||
      c_err "chown gagal — beberapa file mungkin tetap milik root"
  else
    c_err "Butuh sekali jalan untuk memperbaiki izin (tanpa TTY):"
    c_err "  sudo chown -R ${TARGET_USER}: '$ROOT'"
  fi
}

# port aktual yang dipakai proses (fallback ke env/default)
read_port() {
  local portfile="$1"
  if [[ -f "$portfile" ]]; then cat "$portfile"; else echo 0; fi
}

# ---------------------------------------------------------------- ui helpers
c_info() { printf '\033[1;34m[panel]\033[0m %s\n' "$*"; }
c_ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
c_warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
c_err()  { printf '\033[1;31m[err ]\033[0m %s\n' "$*" >&2; }

ensure_dirs() { mkdir -p "$RUN" "$LOGS"; touch -a "$LOGS/backend.log" "$LOGS/frontend.log"; }

# flag hasil preflight (1 = port sudah dilayani instance lain milik panel)
SKIP_BACKEND=0
SKIP_FRONTEND=0
REBUILT=0

# ---------------------------------------------------------------- helpers
alive() {
  # CATATAN: TIDAK boleh pakai `kill -0` — untuk proses milik user lain
  # kill -0 gagal dengan EPERM sehingga proses HIDUP terdeteksi mati
  # (bug asal: stop bilang sukses padahal website masih jalan).
  # `ps -p` bisa melihat proses siapa pun.
  local pidfile="$1" pid
  [[ -f "$pidfile" ]] || return 1
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  ps -p "$pid" -o uid= >/dev/null 2>&1
}

# pemilik proses (nama user) dari isi pidfile; kosong bila tidak ada
owner_of() {
  local pidfile="$1" pid
  [[ -f "$pidfile" ]] || return 0
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] && ps -p "$pid" -o user= 2>/dev/null
}

# true bila pid = salah satu tracked ATAU keturunannya
# (rantai nyata bisa dalam: npm → sh → node → next-server)
related_to_tracked() {
  local pid="$1" tracked="$2" tp cur="$pid" i
  for i in 1 2 3 4 5 6; do
    for tp in $tracked; do
      [[ "$cur" == "$tp" ]] && return 0
    done
    cur="$(ps -o ppid= -p "$cur" 2>/dev/null | tr -d ' ')"
    [[ -z "$cur" || "$cur" == "0" || "$cur" == "1" ]] && return 1
  done
  return 1
}

# Cari PID proses panel yang TIDAK tercatat di .run/*.pid
# (mis. sisa `sudo ./panel.sh start` yang filenya sudah terhapus).
in_container() {
  # cgroup berisi "docker"/"containerd"/"libpod"/"lxc" → proses di dalam
  # container lain (mis. app cloudbox) yang JANGAN disentuh panel.sh
  grep -qE "/(docker|containerd|libpod|lxc)" "/proc/$1/cgroup" 2>/dev/null
}

find_stray_pids() {
  local tracked="$1" only="${2:-}" pd pid cmd
  local found=()
  for pd in /proc/[0-9]*; do
    [[ -r "$pd/cmdline" ]] || continue
    pid="${pd#/proc/}"
    # proses cuma milik panel kalau berada di host (bukan di container lain)
    in_container "$pid" && continue
    cmd="$(tr '\0' ' ' <"$pd/cmdline" 2>/dev/null || true)"
    case "$cmd" in
      *uvicorn*app.main:app*)
        [[ "$only" == "frontend" ]] && continue
        ;;
      *"next-server"*|*"next dev"*)
        [[ "$only" == "backend" ]] && continue
        # Abaikan next-server milik 9router
        local cwd
        cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
        if [[ "$cwd" =~ 9router ]]; then
          continue
        fi
        ;;
      *) continue ;;
    esac
    related_to_tracked "$pid" "$tracked" || found+=("$pid")
  done
  echo "${found[*]:-}"
}

port_open() {
  # subshell menjaga fd tetap terisolasi; JANGAN pakai `exec ... 2>/dev/null`
  # di shell induk — redirect pada exec polos bersifat permanen dan akan
  # menelan stderr panel.sh selamanya.
  if (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; then
    return 0
  fi
  return 1
}

# Tolak start jika port sudah dipakai proses lain.
# Dipanggil sebagai preflight SEBELUM layanan mana pun dijalankan,
# agar tidak ada setengah-instalasi saat salah satu port bentrok.
# $5 = penanda unik dalam respons yang membuktikan pemilik port
#      benar-benar Ubuntu Panel (bukan proses asing).
# Versi kode yang diharapkan — dibaca dari config.py backend.
# Dipakai preflight untuk mendeteksi instans panel LAIN yang masih
# menjalankan kode lama (mis. sisa `sudo ./panel.sh start`).
expected_backend_version() {
  sed -n 's/^    app_version: str = "\(.*\)"/\1/p' \
    "$BACKEND/app/core/config.py" | tail -1
}

preflight_port() {
  local label="$1" varname="$2" port="$3" url="$4" marker="$5"
  port_open "$port" || return 0

  # --max-time wajib: proses asing bisa menerima koneksi tanpa
  # pernah membalas (mis. dev server yang menggantung) → tanpa ini
  # panel.sh bisa menggantung selamanya.
  local body
  body="$(curl -sf --max-time 5 "$url" 2>/dev/null || true)"

  if [[ -n "$body" ]] && [[ "$body" == *"$marker"* ]]; then
    if [[ "$label" == "backend" ]]; then
      local running_ver want_ver
      running_ver="$(printf '%s' "$body" | grep -oE '"version":"[^"]*"' | cut -d'"' -f4 || true)"
      want_ver="$(expected_backend_version || true)"
      if [[ -n "$want_ver" ]] && [[ "$running_ver" != "$want_ver" ]]; then
        c_warn "backend di port ${port} masih memakai kode LAMA (${running_ver:-?} ≠ ${want_ver}) — matikan paksa…"
        # instans lama ini jelas milik Ubuntu Panel sendiri → aman dimatikan
        if can_sudo; then
          sudo -n fuser -k "${port}/tcp" >/dev/null 2>&1 ||
            sudo -p "[sudo] password $(id -un): " fuser -k "${port}/tcp" >/dev/null 2>&1 || true
          sleep 1
          if ! port_open "$port"; then
            c_ok "Port ${port} dibebaskan"
            return 0
          fi
        fi
        c_err "Tidak bisa mengambil alih port ${port} secara otomatis."
        c_err "  Jalankan: sudo fuser -k ${port}/tcp   lalu ulangi: ./panel.sh start"
        exit 1
      fi
    fi
    c_warn "${label}: port ${port} sudah dilayani Ubuntu Panel — start dilewati"
    if [[ "$label" == "backend" ]]; then
      SKIP_BACKEND=1
    else
      SKIP_FRONTEND=1
    fi
  else
    c_err "${label}: port ${port} sedang dipakai proses LAIN."
    c_err "  Matikan proses tersebut, atau ganti port, contoh:"
    c_err "  ${varname}=$((port+1)) ./panel.sh start"
    exit 1
  fi
}

setup_backend() {
  if [[ ! -x "$BACKEND/.venv/bin/python" ]]; then
    c_info "Menyiapkan virtual environment backend…"
    if ! python3 -m venv "$BACKEND/.venv" 2>/dev/null; then
      # fallback jika paket python3-venv/ensurepip tidak tersedia
      rm -rf "$BACKEND/.venv"
      python3 -m venv "$BACKEND/.venv" --without-pip
      python3 -m pip install --quiet \
        --python "$BACKEND/.venv/bin/python" \
        -r "$BACKEND/requirements.txt"
    else
      "$BACKEND/.venv/bin/pip" install --quiet -r "$BACKEND/requirements.txt"
    fi
    touch "$BACKEND/.venv/.requirements.stamp"
    c_ok "Dependensi backend terpasang"
  elif [[ "$BACKEND/requirements.txt" -nt "$BACKEND/.venv/.requirements.stamp" ]]; then
    # requirements.txt berubah sejak instalasi terakhir → perbarui paket
    c_info "Memperbarui dependensi backend…"
    if [[ -x "$BACKEND/.venv/bin/pip" ]]; then
      "$BACKEND/.venv/bin/pip" install --quiet -r "$BACKEND/requirements.txt"
    else
      # CATATAN: opsi --python wajib SEBELUM subcommand install
      python3 -m pip --python "$BACKEND/.venv/bin/python" \
        install --quiet -r "$BACKEND/requirements.txt"
    fi
    touch "$BACKEND/.venv/.requirements.stamp"
    c_ok "Dependensi backend diperbarui"
  fi

  if [[ ! -f "$BACKEND/.env" ]]; then
    c_info "Membuat backend/.env dari template…"
    local secret
    secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    sed "s/^SECRET_KEY=.*/SECRET_KEY=${secret}/" \
      "$BACKEND/.env.example" > "$BACKEND/.env"
    c_warn "backend/.env dibuat dengan admin/admin123 — segera ganti password!"
  fi
}

setup_frontend() {
  if [[ ! -d "$FRONTEND/node_modules" ]]; then
    c_info "Instal dependensi frontend…"
    (cd "$FRONTEND" && npm install --no-audit --no-fund)
    touch "$FRONTEND/node_modules/.deps.stamp"
    c_ok "Dependensi frontend terpasang"
  else
    # package.json / package-lock berubah sejak instalasi terakhir → perbarui
    local mark="$FRONTEND/node_modules/.deps.stamp"
    local deps_stale=0
    if [[ ! -f "$mark" ]]; then
      deps_stale=1
    fi
    if [[ "$FRONTEND/package.json" -nt "$mark" ]]; then
      deps_stale=1
    fi
    if [[ -f "$FRONTEND/package-lock.json" && "$FRONTEND/package-lock.json" -nt "$mark" ]]; then
      deps_stale=1
    fi
    if (( deps_stale )); then
      c_info "Memperbarui dependensi frontend…"
      (cd "$FRONTEND" && npm install --no-audit --no-fund)
      touch "$mark"
      c_ok "Dependensi frontend diperbarui"
    fi
  fi

  # Simpan PORT backend saja — JANGAN URL localhost, agar hostname browser
  # (localhost / IP LAN / IP Tailscale) tetap terdeteksi otomatis di api.ts.
  local want="NEXT_PUBLIC_API_PORT=${BACKEND_PORT}"
  if [[ ! -f "$FRONTEND/.env.local" ]] || ! grep -qx "$want" "$FRONTEND/.env.local"; then
    printf '%s\n' "$want" > "$FRONTEND/.env.local"
  fi
}

build_frontend() {
  local stamp="$RUN/build-backend-port"
  local needs_build=0

  if [[ ! -f "$FRONTEND/.next/BUILD_ID" ]]; then
    needs_build=1
  elif [[ ! -f "$stamp" ]] || [[ "$(cat "$stamp")" != "$BACKEND_PORT" ]]; then
    # port backend berubah sejak build terakhir → bundle lama menunjuk
    # ke port yang salah, wajib rebuild
    needs_build=1
  elif [[ -n "$(find "$FRONTEND/app" "$FRONTEND/components" "$FRONTEND/lib" \
                "$FRONTEND/store" "$FRONTEND/package.json" \
                "$FRONTEND/next.config.mjs" "$FRONTEND/middleware.ts" \
                -newer "$FRONTEND/.next/BUILD_ID" -print -quit 2>/dev/null)" ]]; then
    # ada source yang lebih baru dari bundle terakhir → rebuild
    needs_build=1
  fi

  if [[ "$needs_build" == "1" ]]; then
    c_info "Build frontend…"
    (
      cd "$FRONTEND"
      NEXT_PUBLIC_API_PORT="$BACKEND_PORT" npm run build
    )
    echo "$BACKEND_PORT" > "$stamp"
    REBUILT=1
    c_ok "Build frontend selesai"
  fi
}

# true bila instance tercatat berjalan pada port yang diminta
same_port() {
  [[ -f "$1" ]] && [[ "$(cat "$1" 2>/dev/null)" == "$2" ]]
}

# true bila kode backend berubah sejak start terakhir (auto-restart)
backend_code_changed() {
  local stamp="$RUN/code.backend"
  if [[ ! -f "$stamp" ]]; then
    return 0   # belum ada catatan → perlakukan sebagai berubah
  fi
  if [[ -n "$(find "$BACKEND/app" -type f -name '*.py' \
        -newer "$stamp" -print -quit 2>/dev/null)" ]]; then
    return 0
  fi
  [[ "$BACKEND/requirements.txt" -nt "$stamp" ]]
}

# true bila bundle .next lebih baru dari proses frontend yang sedang hidup.
# Mencegah CSS/JS 400 setelah `npm run build` manual tanpa restart panel.
frontend_bundle_newer_than_process() {
  local pidfile="$1" pid started start_ts build_ts
  [[ -f "$FRONTEND/.next/BUILD_ID" ]] || return 1
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  started="$(ps -p "$pid" -o lstart= 2>/dev/null || true)"
  [[ -n "$started" ]] || return 1
  start_ts="$(date -d "$started" +%s 2>/dev/null || echo 0)"
  build_ts="$(stat -c %Y "$FRONTEND/.next/BUILD_ID" 2>/dev/null || echo 0)"
  (( build_ts > start_ts ))
}

# cegah stop terhadap proses milik user lain (butuh sudo) — gagalkan lebih awal
ensure_owned_or_die() {
  local name="$1" pidfile="$2" owner
  owner="$(owner_of "$pidfile")"
  if [[ -n "$owner" && "$owner" != "$TARGET_USER" ]]; then
    c_err "${name} sedang berjalan milik '${owner}' (PID $(cat "$pidfile")) —"
    c_err "  proses itu tidak bisa saya muat ulang dengan kode baru."
    c_err "  Jalankan: sudo ./panel.sh stop && ./panel.sh start"
    exit 1
  fi
}

start_backend() {
  if alive "$BACKEND_PID_FILE"; then
    if same_port "$BACKEND_PORT_FILE" "$BACKEND_PORT"; then
      if backend_code_changed; then
        ensure_owned_or_die "backend" "$BACKEND_PID_FILE"
        c_warn "Kode backend berubah sejak start terakhir — restart…"
        stop_one "backend" "$BACKEND_PID_FILE" "$BACKEND_PORT_FILE"
      else
        c_ok "Backend sudah berjalan (PID $(cat "$BACKEND_PID_FILE"))"
        return
      fi
    else
      ensure_owned_or_die "backend" "$BACKEND_PID_FILE"
      c_warn "Port backend berubah ($(cat "$BACKEND_PORT_FILE") → ${BACKEND_PORT}) — restart…"
      stop_one "backend" "$BACKEND_PID_FILE" "$BACKEND_PORT_FILE"
    fi
  fi
  if [[ "$SKIP_BACKEND" == "1" ]]; then
    return
  fi
  c_info "Menjalankan backend di port ${BACKEND_PORT}…"
  if am_root && [[ -n "${SUDO_USER:-}" ]]; then
    (
      cd "$BACKEND"
      runuser -u "$TARGET_USER" -- bash -lc "export PATH='/usr/bin:/bin:\$PATH' FRONTEND_PORT='$FRONTEND_PORT' && cd '$BACKEND' && . .venv/bin/activate && setsid python -m uvicorn app.main:app --host 0.0.0.0 --port '$BACKEND_PORT' --timeout-graceful-shutdown 10 >>'$LOGS/backend.log' 2>&1" &
      echo $! > "$BACKEND_PID_FILE"
      echo "$BACKEND_PORT" > "$BACKEND_PORT_FILE"
      touch "$RUN/code.backend"
    )
  else
    (
      cd "$BACKEND"
      setsid env FRONTEND_PORT="$FRONTEND_PORT" .venv/bin/python -m uvicorn app.main:app \
        --host 0.0.0.0 --port "$BACKEND_PORT" --timeout-graceful-shutdown 10 \
        >>"$LOGS/backend.log" 2>&1 &
      echo $! > "$BACKEND_PID_FILE"
      echo "$BACKEND_PORT" > "$BACKEND_PORT_FILE"
      touch "$RUN/code.backend"
    )
  fi
}

start_frontend() {
  if alive "$FRONTEND_PID_FILE"; then
    if same_port "$FRONTEND_PORT_FILE" "$FRONTEND_PORT"; then
      if [[ "$REBUILT" == "1" ]] ||
         frontend_bundle_newer_than_process "$FRONTEND_PID_FILE"; then
        # bundle .next sudah diganti — proses lama masih memegang bundle
        # lama di memori, wajib di-restart agar memakai yang baru
        ensure_owned_or_die "frontend" "$FRONTEND_PID_FILE"
        c_warn "Bundle baru terdeteksi — me-restart frontend…"
        stop_one "frontend" "$FRONTEND_PID_FILE" "$FRONTEND_PORT_FILE"
      else
        c_ok "Frontend sudah berjalan (PID $(cat "$FRONTEND_PID_FILE"))"
        return
      fi
    else
      ensure_owned_or_die "frontend" "$FRONTEND_PID_FILE"
      c_warn "Port frontend berubah ($(cat "$FRONTEND_PORT_FILE") → ${FRONTEND_PORT}) — restart…"
      stop_one "frontend" "$FRONTEND_PID_FILE" "$FRONTEND_PORT_FILE"
    fi
  fi
  if [[ "$SKIP_FRONTEND" == "1" ]]; then
    return
  fi
  if am_root && [[ -n "${SUDO_USER:-}" ]]; then
    if [[ "$DEV_MODE" == "1" ]]; then
      c_info "Menjalankan frontend (mode dev) di port ${FRONTEND_PORT}…"
      (
        cd "$FRONTEND"
        runuser -u "$TARGET_USER" -- bash -lc "export PATH='/usr/bin:/bin:\$PATH' && cd '$FRONTEND' && setsid npm run dev -- -H 0.0.0.0 -p '$FRONTEND_PORT' >>'$LOGS/frontend.log' 2>&1" &
        echo $! > "$FRONTEND_PID_FILE"
        echo "$FRONTEND_PORT" > "$FRONTEND_PORT_FILE"
      )
    else
      c_info "Menjalankan frontend (mode produksi) di port ${FRONTEND_PORT}…"
      (
        cd "$FRONTEND"
        runuser -u "$TARGET_USER" -- bash -lc "export PATH='/usr/bin:/bin:\$PATH' && cd '$FRONTEND' && setsid npm run start -- -H 0.0.0.0 -p '$FRONTEND_PORT' >>'$LOGS/frontend.log' 2>&1" &
        echo $! > "$FRONTEND_PID_FILE"
        echo "$FRONTEND_PORT" > "$FRONTEND_PORT_FILE"
      )
    fi
  elif [[ "$DEV_MODE" == "1" ]]; then
    c_info "Menjalankan frontend (mode dev) di port ${FRONTEND_PORT}…"
    (
      cd "$FRONTEND"
      setsid env PATH="/usr/bin:/bin:$PATH" npm run dev -- -H 0.0.0.0 -p "$FRONTEND_PORT" \
        >>"$LOGS/frontend.log" 2>&1 &
      echo $! > "$FRONTEND_PID_FILE"
      echo "$FRONTEND_PORT" > "$FRONTEND_PORT_FILE"
    )
  else
    c_info "Menjalankan frontend (mode produksi) di port ${FRONTEND_PORT}…"
    (
      cd "$FRONTEND"
      setsid env PATH="/usr/bin:/bin:$PATH" npm run start -- -H 0.0.0.0 -p "$FRONTEND_PORT" \
        >>"$LOGS/frontend.log" 2>&1 &
      echo $! > "$FRONTEND_PID_FILE"
      echo "$FRONTEND_PORT" > "$FRONTEND_PORT_FILE"
    )
  fi
}

wait_ready() {
  local name="$1" url="$2" pidfile="$3" skip="${4:-0}" i
  printf '\033[1;34m[panel]\033[0m Menunggu %s siap' "$name"
  for i in $(seq 1 60); do
    # cek proses kita dulu — kalau mati, jangan tertipu oleh jawaban
    # healthy dari instans lain yang kebetulan memegang port
    if [[ "$skip" != "1" ]] && ! alive "$pidfile"; then
      printf ' \033[1;31mmati\033[0m\n'
      c_err "$name keluar saat startup — lihat $LOGS/${name}.log"
      c_err "Kemungkinan port sudah dipakai instans lain (mis. dijalankan sebagai root). Cek: ss -tlnp | grep ${url##*:}"
      return 1
    fi
    if curl -sf --max-time 3 -o /dev/null "$url"; then
      # Simpan PID proses yang BENAR-BENAR memegang port. Saat start lewat
      # runuser/setsid, $! bisa menunjuk wrapper, bukan uvicorn/next-server,
      # sehingga stop berikutnya meninggalkan proses orphan.
      if [[ "$skip" != "1" ]]; then
        local real_pid
        real_pid="$(ss -ltnpH "sport = :${url##*:}" 2>/dev/null \
          | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true)"
        [[ -n "$real_pid" ]] && printf '%s\n' "$real_pid" > "$pidfile" 2>/dev/null || true
      fi
      printf ' \033[1;32mready\033[0m\n'
      return 0
    fi
    printf '.'
    sleep 0.5
  done
  printf ' \033[1;31mgagal\033[0m\n'
  c_err "$name tidak merespons. Cek log: $LOGS"
  return 1
}

stop_panel_pid() {
  local pid="$1" sig="$2" owner
  owner="$(ps -p "$pid" -o user= 2>/dev/null | tr -d ' ')"
  if [[ "$(id -u)" == "0" || "$owner" == "$(id -un)" ]]; then
    kill "-${sig}" "$pid" 2>/dev/null || true
  elif can_sudo; then
    sudo -n kill "-${sig}" "$pid" 2>/dev/null ||
      sudo -p "[sudo] password $(id -un): " kill "-${sig}" "$pid" 2>/dev/null || true
  fi
}

stop_one() {
  local name="$1" pidfile="$2" portfile="$3" pid i owner port tracked strays stray stopped=0
  port="$(cat "$portfile" 2>/dev/null || true)"
  if alive "$pidfile"; then
    pid="$(cat "$pidfile")"
    owner="$(owner_of "$pidfile")"
    c_info "Menghentikan ${name} (PID ${pid}${owner:+, user ${owner}})…"
    # hentikan seluruh process group (fallback: proses utamanya saja)
    kill -- "-${pid}" 2>/dev/null || kill "$pid" 2>/dev/null || true
    for i in $(seq 1 20); do
      alive "$pidfile" || break
      sleep 0.5
    done
    if alive "$pidfile"; then
      stop_panel_pid "$pid" 9
      sleep 0.5
    fi
    if alive "$pidfile"; then
      # JANGAN hapus pidfile — tracking harus tetap ada agar stop/status
      # berikutnya masih melihat proses ini.
      c_err "${name} (PID ${pid}) tidak bisa dihentikan — proses milik '${owner:-?}'."
      c_err "  Jalankan: sudo ./panel.sh stop   atau: sudo fuser -k ${port:-?}/tcp"
      return 1
    fi
    stopped=1
  fi

  # PID di pidfile bisa menunjuk wrapper runuser/setsid, atau proses aslinya
  # sudah lepas menjadi orphan. Bersihkan sisa proses panel yang memegang port.
  tracked="$(cat "$pidfile" 2>/dev/null || true)"
  strays="$(find_stray_pids "$tracked" "$name" 2>/dev/null || true)"
  for stray in $strays; do
    owner="$(ps -p "$stray" -o user= 2>/dev/null | tr -d ' ')"
    c_warn "${name}: proses panel tak tercatat (PID ${stray}${owner:+, user ${owner}}) — hentikan…"
    stop_panel_pid "$stray" TERM
    stopped=1
  done
  for i in $(seq 1 10); do
    strays="$(find_stray_pids "$tracked" "$name" 2>/dev/null || true)"
    [[ -z "$strays" ]] && break
    sleep 0.5
  done
  for stray in $strays; do
    stop_panel_pid "$stray" 9
  done

  if [[ -n "$port" ]] && port_open "$port"; then
    c_err "${name}: port ${port} masih dipakai setelah proses dihentikan."
    c_err "  Jalankan: sudo fuser -k ${port}/tcp"
    return 1
  fi
  rm -f "$pidfile" "$portfile"
  if (( stopped )); then
    c_ok "${name} dihentikan"
  else
    c_warn "${name} memang tidak sedang berjalan"
  fi
  return 0
}

# ---------------------------------------------------------------- commands
cmd_start() {
  ensure_dirs
  reclaim_runtime_files

  if [[ "$BACKEND_PORT" == "$FRONTEND_PORT" ]]; then
    c_err "BACKEND_PORT dan FRONTEND_PORT tidak boleh sama (${BACKEND_PORT})"
    exit 1
  fi

  setup_backend
  setup_frontend

  # cek kedua port lebih dulu — jangan sampai satu layanan terlanjur
  # jalan lalu gagal karena port layanan satunya bentrok
  preflight_port "backend"  "BACKEND_PORT"  "$BACKEND_PORT" \
    "http://127.0.0.1:${BACKEND_PORT}/api/health" '"status"'
  preflight_port "frontend" "FRONTEND_PORT" "$FRONTEND_PORT" \
    "http://127.0.0.1:${FRONTEND_PORT}/login" "Ubuntu Server Manager"

  # masih ada instans milik user lain? hentikan via sudo agar panel
  # berjalan penuh sebagai user ini (pidfile/log tidak jadi milik root)
  if ! am_root && has_foreign_targets && can_sudo; then
    c_warn "Menghentikan instans milik user lain agar panel jalan sebagai $(id -un)…"
    sudo -n bash "$SELF" _stop-inner 2>/dev/null ||
      sudo -p "[sudo] password $(id -un): " bash "$SELF" _stop-inner || true
  fi

  # selalu pastikan bundle frontend cocok dengan BACKEND_PORT terkini
  # (dijalankan sebelum start, termasuk saat frontend di-skip/restart)
  build_frontend

  start_backend
  start_frontend
  wait_ready "backend"  "http://127.0.0.1:${BACKEND_PORT}/api/health" "$BACKEND_PID_FILE"  "$SKIP_BACKEND"
  wait_ready "frontend" "http://127.0.0.1:${FRONTEND_PORT}/login"     "$FRONTEND_PID_FILE" "$SKIP_FRONTEND"

  # deteksi IP LAN + Tailscale (jika ada) untuk ditampilkan.
  # IP LAN diambil dari sumber rute default (interface fisik),
  # lalu dibuang bila ternyata menunjuk ke interface tailnet.
  TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  LAN_IF="$(ip -4 route show default 2>/dev/null | awk '{print $5; exit}' || true)"
  LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null \
    | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)"
  if [[ "$LAN_IF" == "tailscale0" ]] \
    || [[ -n "$TAILSCALE_IP" && "$LAN_IP" == "$TAILSCALE_IP" ]]; then
    LAN_IP=""
    LAN_IF=""
  fi

  echo
  c_ok "Ubuntu Panel berjalan:"
  echo "    • Panel     : http://localhost:${FRONTEND_PORT}"
  if [[ -n "$LAN_IP" ]]; then
    echo "    • LAN       : http://${LAN_IP}:${FRONTEND_PORT}"
  fi
  if [[ -n "$TAILSCALE_IP" ]]; then
    echo "    • Tailscale : http://${TAILSCALE_IP}:${FRONTEND_PORT}"
  fi
  echo "    • API       : http://localhost:${BACKEND_PORT}/api/docs"
  echo "    • Log       : $LOGS/backend.log · $LOGS/frontend.log"
  echo "    • Berhenti  : ./panel.sh stop"
  echo
  if [[ -n "$LAN_IP" ]]; then
    c_info "Akses dari komputer lain di LAN (${LAN_IF:-lan}): http://${LAN_IP}:${FRONTEND_PORT}"
    c_warn "Jika diblokir, izinkan interface ${LAN_IF:-lan} di UFW:"
    c_warn "  sudo ufw allow in on ${LAN_IF:-lan} to any port ${FRONTEND_PORT},${BACKEND_PORT} proto tcp"
  fi
  if [[ -n "$TAILSCALE_IP" ]]; then
    c_info "Akses dari perangkat lain di tailnet: http://${TAILSCALE_IP}:${FRONTEND_PORT}"
    c_warn "Jika diblokir, izinkan interface tailscale0 di UFW:"
    c_warn "  sudo ufw allow in on tailscale0 to any port ${FRONTEND_PORT},${BACKEND_PORT} proto tcp"
  fi
}

stop_all_impl() {
  local failed=0
  stop_one "frontend" "$FRONTEND_PID_FILE" "$FRONTEND_PORT_FILE" || failed=1
  stop_one "backend"  "$BACKEND_PID_FILE"  "$BACKEND_PORT_FILE"  || failed=1

  # proses panel liar (tidak tercatat pidfile) — sisa start sebagai
  # user lain / file pid terhapus
  local tracked strays stray owner
  tracked="$(cat "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE" 2>/dev/null || true)"
  strays="$(find_stray_pids "$tracked")"
  for stray in $strays; do
    owner="$(ps -p "$stray" -o user= 2>/dev/null | tr -d ' ')"
    if [[ "$owner" == "$TARGET_USER" ]] || am_root; then
      c_warn "Menemukan proses liar (PID ${stray}, user ${owner:-?}) — dihentikan…"
      kill "$stray" 2>/dev/null || true
    else
      c_err "Masih ada proses panel milik '${owner:-?}' (PID ${stray}) yang tidak bisa saya hentikan."
      c_err "  Jalankan: sudo ./panel.sh stop   atau: sudo fuser -k ${BACKEND_PORT}/tcp ${FRONTEND_PORT}/tcp"
      failed=1
    fi
  done

  if (( failed )); then
    c_err "Tidak semua proses bisa dihentikan — website/API kemungkinan masih jalan."
    return 1
  fi
  return 0
}

# true bila ada proses panel yang dimiliki user lain (butuh sudo)
has_foreign_targets() {
  local pf owner tracked strays stray o
  for pf in "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"; do
    owner="$(owner_of "$pf")"
    [[ -n "$owner" && "$owner" != "$TARGET_USER" ]] && return 0
  done
  tracked="$(cat "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE" 2>/dev/null || true)"
  strays="$(find_stray_pids "$tracked" 2>/dev/null || true)"
  for stray in $strays; do
    o="$(ps -p "$stray" -o user= 2>/dev/null | tr -d ' ')"
    [[ -n "$o" && "$o" != "$TARGET_USER" ]] && return 0
  done
  return 1
}

cmd_stop() {
  # proses milik user lain (mis. sisa `sudo ./panel.sh start`) tidak bisa
  # dikill sebagai user biasa → ulangi seluruh stop sebagai root sekali.
  if ! am_root && has_foreign_targets && can_sudo; then
    c_warn "Proses panel milik user lain terdeteksi — ambil alih via sudo…"
    if sudo -n bash "$SELF" _stop-inner 2>/dev/null; then
      c_ok "Semua proses Ubuntu Panel berhenti"
      return 0
    fi
    if sudo -p "[sudo] password ${TARGET_USER}: " bash "$SELF" _stop-inner; then
      c_ok "Semua proses Ubuntu Panel berhenti"
      return 0
    fi
    c_err "Stop via sudo gagal — dicoba lagi tanpa sudo…"
  fi
  stop_all_impl
}

cmd_status() {
  local state pid port owner extra
  for entry in "backend:$BACKEND_PID_FILE:$BACKEND_PORT_FILE:/api/health" \
               "frontend:$FRONTEND_PID_FILE:$FRONTEND_PORT_FILE:/login"; do
    IFS=':' read -r name pidfile portfile path <<< "$entry"
    port="$(read_port "$portfile")"
    [[ "$port" == "0" ]] && port="(belum ada)"
    if alive "$pidfile"; then
      pid="$(cat "$pidfile")"
      owner="$(owner_of "$pidfile")"
      extra=""
      if [[ -n "$owner" ]] && [[ "$owner" != "$TARGET_USER" ]]; then
        extra=" \033[1;33m[milik ${owner} — stop butuh sudo]\033[0m"
      fi
      if curl -sf --max-time 3 -o /dev/null "http://127.0.0.1:${port}${path}"; then
        state="\033[1;32mrunning\033[0m"
      else
        state="\033[1;33mstarting/unhealthy\033[0m"
      fi
      printf '%-9s %-19s (PID %s, port %s)%b\n' "$name" "$(printf "$state")" "$pid" "$port" "$extra"
    else
      printf '%-9s \033[1;31mstopped\033[0m\n' "$name"
    fi
  done

  # peringatkan bila ada proses panel liar yang tidak tercatat
  local tracked strays stray owner
  tracked="$(cat "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE" 2>/dev/null || true)"
  strays="$(find_stray_pids "$tracked")"
  for stray in $strays; do
    owner="$(ps -p "$stray" -o user= 2>/dev/null | tr -d ' ')"
    c_warn "instans tak tercatat: PID ${stray} (user ${owner:-?}) — stop/status mungkin tidak akurat"
  done
}

cmd_logs() {
  local target="${1:-all}"
  case "$target" in
    backend)  tail -n 50 -F "$LOGS/backend.log" ;;
    frontend) tail -n 50 -F "$LOGS/frontend.log" ;;
    all)      tail -n 30 -F "$LOGS/backend.log" "$LOGS/frontend.log" ;;
    *) c_err "Target log tidak dikenal: $target (pakai backend|frontend|all)"; exit 1 ;;
  esac
}

cmd_help() {
  cat <<EOF
Ubuntu Panel launcher

Pemakaian:
  ./panel.sh start                     Jalankan backend + frontend
  ./panel.sh stop                      Hentikan keduanya
  ./panel.sh restart                   Restart keduanya
  ./panel.sh status                    Lihat status tiap layanan
  ./panel.sh logs [backend|frontend]   Ikuti log (default: all)

Variabel lingkungan:
  BACKEND_PORT=8000    Port API FastAPI
  FRONTEND_PORT=3000   Port web Next.js
  DEV=1                Mode development (hot-reload)

Contoh:
  DEV=1 ./panel.sh start
  FRONTEND_PORT=3001 ./panel.sh start
EOF
}

case "${1:-help}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  # internal: dieksekusi via `sudo bash panel.sh _stop-inner` — stop murni
  # tanpa deteksi/elevasi supaya tidak memanggil sudo berulang
  _stop-inner) ensure_dirs; stop_all_impl ;;
  restart)
    cmd_stop || true          # stop gagal pun lanjut — start akan bereskan
    ensure_dirs
    cmd_start
    ;;
  status)  cmd_status ;;
  logs)    shift; cmd_logs "${1:-all}" ;;
  help|--help|-h) cmd_help ;;
  *) c_err "Perintah tidak dikenal: $1"; cmd_help; exit 1 ;;
esac
