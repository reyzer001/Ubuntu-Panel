# Stack & Struktur — Ubuntu Panel

Versi update: 2026-08-29

Dokumen ini menjelaskan stack dan arsitektur yang benar-benar ada di proyek saat ini, termasuk fitur tambahan yang berkembang setelah rencana awal.

---

## Arsitektur Umum

```text
Browser (Next.js + Tailwind)
        │
        ▼
FastAPI Backend (Uvicorn)
        │
        ├── REST API
        ├── WebSocket /api/ws/metrics
        ├── Background schedulers
        └── SQLite DB + system adapters
        │
        ├── psutil                  -> CPU/RAM/Disk/Network metrics
        ├── subprocess/systemctl    -> services, firewall, journalctl, apt
        ├── Docker SDK             -> container management
        ├── Cloudflare tunnel      -> website exposure
        └── Python agent protocol  -> remote computer discovery + heartbeat

Frontend -> Backend via Next.js API proxy
Agent -> Backend via UDP discovery + HTTP/JSON heartbeat
```

**Prinsip:** proyek masih berbasis monolitik pada satu backend, tetapi sudah berkembang ke arah “hybrid single-panel + remote agent support”.

---

## Stack Teknologi

### Frontend

| Komponen | Teknologi |
|----------|-----------|
| Framework | Next.js 14 |
| Language | TypeScript |
| UI | React + Tailwind CSS |
| Charts | Recharts |
| State | TanStack Query + Zustand |
| Icons | Lucide React |
| Utilities | clsx |

### Backend

| Komponen | Teknologi |
|----------|-----------|
| Framework | FastAPI |
| Server | Uvicorn |
| Language | Python 3.12 |
| ORM | SQLAlchemy |
| Validation | Pydantic |
| Auth | JWT HS256 |
| Metrics | psutil |
| Container | Docker SDK |
| Upload | python-multipart |
| Config | pydantic-settings |

### Database

| Komponen | Teknologi |
|----------|-----------|
| Database | SQLite (WAL mode) |
| File | backend/ubuntu-panel.db |
| Migration | Manual auto-migration via seed / startup logic |

### Operational support

| Komponen | Teknologi |
|----------|-----------|
| Process manager | panel.sh |
| Tunnel | Cloudflare Quick Tunnel |
| Background jobs | Python threads/scheduler |
| Remote agent | Python standalone agent |
| Discovery | UDP broadcast listener |

---

## Arsitektur Fungsional

### 1. Core Panel

Backend utama menangani fungsi server lokal seperti:

* monitoring system
* service management
* files and storage
* firewall
* users
* logs
* docker
* backup
* maintenance

### 2. Web App & Website Management

Panel juga menjalankan fitur website/dev-server management:

* app registry
* runtime orchestration
* service logs
* tunnel exposure
* local app monitoring

### 3. Access Points + Topology

Ada monitoring khusus untuk perangkat jaringan:

* AP scan
* inventory access points
* grouping
* event tracking
* AP-to-device correlation

### 4. Remote Computer Management

Project sudah memiliki subsystem agent untuk komputer lain sebagai node monitor:

* agent discovery
* heartbeat
* OS metadata
* connectivity info
* AP/SSID info
* speed test metadata

---

## Struktur Repository

```text
Ubuntu-Panel/
├── README.md
├── Rencana.md
├── Stack&Structur.md
├── Prototype.md
├── panel.sh
├── tunnel.sh
├── agent/
│   ├── agent.ini
│   ├── agent.ini.example
│   ├── panel_agent.py
│   └── build-linux.sh
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── deps.py
│   │   │   └── security.py
│   │   ├── db/
│   │   │   ├── database.py
│   │   │   ├── models.py
│   │   │   └── seed.py
│   │   ├── routers/
│   │   │   ├── accesspoints.py
│   │   │   ├── auth.py
│   │   │   ├── backup.py
│   │   │   ├── computers.py
│   │   │   ├── docker.py
│   │   │   ├── files.py
│   │   │   ├── firewall.py
│   │   │   ├── logs.py
│   │   │   ├── maintenance.py
│   │   │   ├── panel_users.py
│   │   │   ├── processes.py
│   │   │   ├── services.py
│   │   │   ├── system.py
│   │   │   ├── terminal.py
│   │   │   ├── users.py
│   │   │   └── websites.py
│   │   └── services/
│   │       ├── apmon.py
│   │       ├── audit.py
│   │       ├── backup.py
│   │       ├── collectors.py
│   │       ├── dbcleanup.py
│   │       ├── maintenance.py
│   │       ├── topology.py
│   │       └── websites.py
│   ├── data/
│   │   ├── oui.txt
│   │   └── weblogs/
│   ├── requirements.txt
│   └── tests/
│
├── frontend/
│   ├── app/
│   │   ├── (panel)/
│   │   │   ├── access-points/
│   │   │   ├── backup/
│   │   │   ├── computer-management/
│   │   │   ├── dashboard/
│   │   │   ├── docker/
│   │   │   ├── firewall/
│   │   │   ├── logs/
│   │   │   ├── maintenance/
│   │   │   ├── network/
│   │   │   ├── processes/
│   │   │   ├── services/
│   │   │   ├── storage/
│   │   │   ├── terminal/
│   │   │   ├── user-management/
│   │   │   ├── users/
│   │   │   └── websites/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   ├── login/
│   │   └── page.tsx
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   ├── store/
│   ├── next.config.mjs
│   ├── package.json
│   ├── postcss.config.mjs
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
└── trae-agent/
    └── additional AI tooling / project experiments
```

---

## Database Models Penting

| Model | Fungsi |
|-------|--------|
| `User` | panel user login |
| `AuditLog` | log aktivitas |
| `BackupJob` | konfigurasi backup |
| `BackupRun` | riwayat backup |
| `APScanTarget` | target scan AP |
| `APGroup` | grouping access point |
| `AccessPoint` | inventory perangkat jaringan |
| `APEvent` | log event AP |
| `ManagedComputer` | komputer remote dari agent |
| `WebApp` | aplikasi website lokal |
| `WebService` | service di dalam aplikasi web |

---

## API Pendekatan

```text
/api/auth
/api/system
/api/services
/api/processes
/api/logs
/api/users
/api/panel-users
/api/docker
/api/firewall
/api/terminal
/api/backup
/api/maintenance
/api/access-points
/api/websites
/api/computers
/api/files
```

---

## Catatan Arsitektur

1. Proyek masih menggunakan SQLite sebagai database utama, bukan PostgreSQL.
2. Backend masih merupakan pusat operasional, tetapi sekarang ada dukungan untuk agent remote.
3. Frontend dan backend dipisah tetapi tetap saling di-proxy untuk pengembangan dan deployment.
4. Background workers sudah menjadi bagian penting dari aplikasi, bukan hanya fitur tambahan.
5. Keamanan masih diutamakan melalui validasi command, JWT, dan pembatasan akses write.

---

## Kesimpulan

Struktur saat ini lebih kompleks dari versi awal. Project ini bukan sekadar panel monitoring Ubuntu single-server, tetapi sudah bergerak ke arah:

* server operations dashboard
* remote machine monitoring
* local website lifecycle management
* topology and access point awareness
* background automation and scheduler management

Jadi, dokumentasi awal masih valid untuk fondasi, tetapi perlu dipahami sebagai versi dasar dari arsitektur yang sudah berkembang lebih jauh.

| Role | Permission |
|------|-----------|
| `superadmin` | Full access. Bisa manage panel users. |
| `admin` | Full access ke semua fitur server. Tidak bisa manage panel users. |
| `viewer` | Read-only. Tidak bisa execute action apapun. |

Auth flow:
1. Login → `POST /api/auth/login` → dapat JWT token
2. Token disimpan di Zustand (localStorage)
3. Semua request kirim `Authorization: Bearer <token>`
4. 401 → auto-logout → redirect ke `/login`

---

## Background Jobs (Thread-based)

| Job | Interval | Fungsi |
|-----|----------|--------|
| Web Monitor | 4 detik | Sync status service + tunnel |
| AP Monitor | 10 detik | Ping sweep online/offline |
| AP Scanner | 5 menit | Auto-scan subnet targets |
| Backup Scheduler | 1 menit | Check cron schedule, run due jobs |
| Metrics WebSocket | On-connect | Push live metrics ke browser |

Semua berjalan sebagai Python `threading.Thread(daemon=True)`.

---

## Deployment

### Cara Jalankan

```bash
# Start backend + frontend
./panel.sh start

# Start Cloudflare tunnel (akses online)
./tunnel.sh start
```

### Port

| Service | Port |
|---------|------|
| Frontend (Next.js) | 3000 |
| Backend (FastAPI/uvicorn) | 8000 |
| Cloudflare Tunnel | Random (trycloudflare.com) |

### Website Online Access

Tombol **Online** pada Menagement Website selalu menggunakan `cloudflared`, bukan
membuka port website secara langsung ke internet. Tunnel dibuat untuk service
website yang sedang aktif dan diarahkan ke `http://localhost:<resolved_port>`.
URL `trycloudflare.com` disimpan per service dan ditampilkan di Website
Management setelah berhasil terdeteksi dari log `cloudflared`.

Tombol **Offline** menghentikan proses `cloudflared` milik service tersebut,
sedangkan **Stop** menghentikan proses website. Karena itu website harus aktif
lebih dahulu sebelum dapat di-online-kan. Untuk akses produksi dengan domain
tetap, Quick Tunnel dapat diganti Cloudflare named tunnel tanpa mengubah alur
Menagement Website.

### Environment Variables

**Backend** (`backend/.env`):
```
SECRET_KEY=<random>
ACCESS_TOKEN_EXPIRE_MINUTES=720
DATABASE_URL=sqlite:///./ubuntu-panel.db
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
CORS_ORIGINS=["*"]
```

**Frontend** (`frontend/.env.local`):
```
NEXT_PUBLIC_API_PORT=8000
NEXT_PUBLIC_USE_PROXY=1
```

---

## Perbedaan dari Rencana Awal

| Aspek | Rencana Awal | Aktual |
|-------|-------------|--------|
| Database | PostgreSQL | **SQLite** (WAL) |
| Cache | Redis | **Tidak ada** |
| Agent | Go (systemd service) | **Python script** (standalone) |
| ORM Migration | Alembic | **Manual ALTER TABLE** |
| Task Queue | Celery | **threading.Thread** |
| Metrics | Prometheus | **WebSocket + in-memory** |
| Reverse Proxy | Nginx | **Next.js rewrites** |
| Deployment | Docker Compose | **panel.sh** (bare metal) |
| UI Library | shadcn/ui | **Custom Tailwind** |
| Auth | RBAC (3 role) | **JWT + 3 role** (sudah sesuai) |
| API Versioning | /api/v1/ | **/api/** (tanpa versi) |
| Rate Limiting | Ada | **Tidak ada** |
| CSRF Protection | Ada | **Tidak ada** (rely on Bearer token) |

**Alasan perubahan:** Ubuntu Panel diimplementasikan sebagai aplikasi single-server yang ringan dan langsung jalan tanpa container/orchestration. SQLite cukup untuk panel single-user. Background threads cukup untuk job scheduler skala kecil. Tidak perlu Redis/Prometheus untuk satu server.
