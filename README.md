# Ubuntu Panel

Single-server web panel untuk manajemen Ubuntu Server — dibangun sesuai tiga
dokumen rancangan di repo ini:

| Dokumen | Isi |
| --- | --- |
| `Rencana.md` | Daftar fitur & struktur menu (V1 = 10 halaman) |
| `Stack&Structur.md` | Pilihan stack (V1 single-server: tanpa agent Go, Redis, Prometheus) |
| `Prototype.md` | Desain UI yang di-porting ke Tailwind |

## Arsitektur V1 (single-server)

```text
Browser (Next.js + Tailwind + TanStack Query + Recharts)
   │  HTTPS / WebSocket
   ▼
FastAPI (auth JWT, audit log, REST + WS)
   │  psutil · systemctl · journalctl · ufw · Docker SDK
   ▼
Ubuntu host
```

Tidak ada agent terpisah — backend berjalan langsung di server yang dikelola.
Layer agent Go/Prometheus/Redis disiapkan nanti untuk mode multi-server.

## Fitur V1

- **Login** — JWT (12 jam), password PBKDF2, audit log semua aksi
- **Dashboard** — health card, CPU/RAM/Disk/Load realtime via WebSocket,
  grafik riwayat, critical services, storage bars, network, recent activity
- **Services** — daftar unit systemd + start/stop/restart
- **Processes** — daftar proses, sort CPU/RAM/PID, kill (dengan konfirmasi)
- **Logs** — journalctl, filter level (INFO/WARN/ERROR), search, export .txt
- **Storage** — filesystem per mount point + inode usage + disk I/O live,
  file manager: browse, upload (dengan progres), download, buat folder, hapus —
  bisa dipakai dari localhost, IP LAN, maupun IP Tailscale
- **Network** — interface, RX/TX live, koneksi established, listening ports
- **Docker** — daftar container + start/stop/restart (opsional)
- **Websites** — run/stop dev-server per folder (native) atau satu-file Docker image
  (build + sync). Dukung runtime tambahan **Docker Compose**: kirimkan proyek
  beserta `docker-compose.yml`, panel jalankan `docker compose up -d --build` dan
  lacak status (ONLINE/OFFLINE) via container. Cocok untuk project seperti
  CloudBox yang paketnya satu compose unit.
- **Firewall** — status UFW, lihat/tambah/hapus rule (ter-audit)
- **Users** — daftar akun lokal, create/delete user (root dilindungi)
- **Terminal** — command interface terbatas (whitelist), **bukan shell bebas**
- **Backup** — job backup panel/direktori/config/MySQL/PostgreSQL, jadwal cron
  internal, retensi otomatis, riwayat, unduh arsip, restore aman (ekstrak ke
  folder terpisah, tidak pernah menimpa data live)
- **Maintenance** — vacuum journal & bersih-bersih cache apt, `apt update` /
  `upgrade` sebagai task dengan output live, reboot berkonfirmasi
- **Access Points** — monitoring AP kantor via LAN tanpa kontroller: ARP sweep
  subnet (dikonfigurasi via UI), MAC/IP otomatis, merk via database OUI,
  SSID otomatis bila server punya WiFi adapter (`iw scan` cocok BSSID) atau
  diisi manual, status online/offline persisten + log kejadian. Scan tiap
  5 menit (env `AP_SCAN_INTERVAL`). Opsional: `sudo apt install arp-scan`
  untuk sweep lebih cepat; letakkan `oui.txt` IEEE di `backend/data/` bila
  server tanpa internet agar nama merk terdeteksi.

Keamanan sesuai Rencana.md: tidak ada eksekusi shell arbitrer; nama service,
container, port, dan username divalidasi regex sebelum sampai ke subprocess.

## Menjalankan

### Cara cepat — script `panel.sh`

Dari root proyek (tanpa masuk ke folder backend/frontend):

```bash
./panel.sh start        # jalankan semua (auto-setup venv, deps, build)
./panel.sh status       # cek status tiap layanan
./panel.sh logs         # ikuti log (atau: logs backend / logs frontend)
./panel.sh stop         # hentikan semua
```

Opsi lewat environment variable:

```bash
DEV=1 ./panel.sh start              # mode development (hot-reload)
FRONTEND_PORT=3001 ./panel.sh start # ganti port web
BACKEND_PORT=9000 ./panel.sh start  # ganti port API
```

Script otomatis: membuat `.venv` + install requirements saat pertama kali,
membuat `backend/.env` dengan SECRET_KEY acak, `npm install`, build frontend,
lalu menunggu kedua layanan siap sebelum melapor.

> Catatan akses jaringan: backend bind di `0.0.0.0` dan frontend otomatis
> memakai hostname browser sebagai alamat API, jadi dashboard bisa dibuka
> via `localhost`, IP LAN, maupun **IP Tailscale** tanpa rebuild. `panel.sh`
> menampilkan URL Tailscale otomatis bila `tailscale` terdeteksi. Jika UFW
> memblokir, izinkan interface tailnet:
>
> ```bash
> sudo ufw allow in on tailscale0 to any port 3000,8000 proto tcp
> ```
>
> Untuk mengunci ke origin tertentu, set `CORS_ORIGINS` di `backend/.env`.

### Manual

#### Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # ganti SECRET_KEY & ADMIN_PASSWORD!
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Saat pertama jalan, database SQLite dibuat otomatis + user admin dari env
`ADMIN_USERNAME` / `ADMIN_PASSWORD` (default `admin` / `admin123`).

> Beberapa fitur (melihat proses listening port, mengelola UFW) butuh akses
> root. Untuk produksi jalankan backend sebagai systemd service dengan user
> khusus + sudoers granular, bukan sebagai root penuh.

### Frontend (Next.js)

```bash
cd frontend
npm install
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev                   # http://localhost:3000
```

Produksi: `npm run build && npm run start`.

## Struktur

```text
Ubuntu-Panel/
├── backend/
│   ├── app/
│   │   ├── core/        # config, security (JWT+PBKDF2), deps
│   │   ├── db/          # SQLAlchemy models, seed admin
│   │   ├── routers/     # auth, system, services, processes, logs,
│   │   │                # users, docker, firewall, terminal,
│   │   │                # backup, maintenance
│   │   └── services/    # collectors (psutil/systemctl/...), audit,
│   │                    # backup engine + scheduler, maintenance
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── login/
│   │   └── (panel)/     # dashboard, services, processes, logs,
│   │                    # storage, network, docker, firewall,
│   │                    # users, terminal
│   ├── components/      # sidebar, page-header, ui/*
│   ├── hooks/           # use-metrics-stream (WebSocket)
│   ├── lib/             # api client, types, format
│   └── store/           # zustand auth
├── Prototype.md         # desain UI acuan
├── Rencana.md           # rencana fitur
└── Stack&Structur.md    # arsitektur stack
```

## Roadmap (fase berikutnya)

1. RBAC (Admin/Operator/Viewer) + halaman manajemen user panel
2. Audit log viewer di UI
3. Halaman Packages, Cron, Alerts (rencana #10, #13, #14)
4. Mode multi-server: agent Go outbound-ke-backend + Prometheus

> Backup (#12) dan Maintenance (cleanup + update sistem) sudah tersedia.
> Aksi apt/journal butuh passwordless sudo untuk user backend, contoh
> `/etc/sudoers.d/ubuntu-panel`:
>
> ```
> eta ALL=(root) NOPASSWD: /usr/bin/apt-get, /usr/bin/journalctl, /usr/bin/systemctl reboot
> ```
