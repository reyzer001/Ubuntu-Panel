# Rencana & Status Fitur — Ubuntu Panel

Versi update: 2026-08-29

Status utama: **DONE** untuk fitur inti, **PARTIAL** untuk batasan keamanan / operasional, **PLAN** untuk roadmap lanjutan.

---

## 1. Dashboard / Overview

**Status: DONE**

Halaman utama menampilkan ringkasan real-time server, termasuk:

* CPU, memory, disk usage
* Load average
* Network in/out realtime
* Uptime
* Jumlah proses dan user login
* Health status: Healthy / Warning / Critical
* Grafik rolling history CPU, memory, disk I/O, network, dan load average
* Informasi sistem: hostname, OS, kernel, IP, boot time
* WebSocket `/api/ws/metrics` untuk live metrics

---

## 2. Server Information

**Status: DONE**

Detail sistem tersedia di dashboard dan endpoint system info.

Yang ditampilkan:

* Hostname
* IP address
* Distro dan versi OS
* Kernel dan arsitektur
* CPU model dan core/thread
* RAM total
* Boot time
* Virtualization type jika ada

---

## 3. Process Manager

**Status: DONE**

Halaman `processes` menyediakan:

* Daftar proses dengan PID, user, CPU, RAM, command
* Sort by CPU / RAM / Name
* Search/filter
* Kill process dengan konfirmasi

---

## 4. Service Management (systemd)

**Status: DONE**

Halaman `services` memungkinkan:

* List semua unit systemd
* Start / Stop / Restart
* Enable / Disable
* Status indicator
* Action dengan konfirmasi

---

## 5. Disk & Storage

**Status: DONE**

Halaman `storage` mencakup:

* Filesystem list per mountpoint
* Disk I/O live
* INODE usage
* File manager dengan browse, breadcrumbs, upload, download, mkdir, delete
* Sort by name/size/modified
* Show/hide hidden files
* Upload besar via backend direct upload

---

## 6. Network Management

**Status: DONE**

Halaman `network` menampilkan:

* Interface list
* MAC, IPv4/IPv6, RX/TX bytes, speed
* Live traffic rate
* Listening ports
* Established connections

---

## 7. Firewall (UFW)

**Status: DONE**

Fitur utama:

* Status UFW enabled/disabled
* Daftar rules
* Add rule port/protocol/action
* Delete rule

---

## 8. Users (Linux OS)

**Status: DONE**

Halaman `users` menangani:

* Daftar akun lokal
* Create user
* Delete user

---

## 9. Panel Users / RBAC

**Status: DONE (basic)**

Panel memiliki fitur akun panel sendiri, bukan hanya user OS:

* Login via JWT
* Role: superadmin / admin / viewer
* CRUD panel users
* Audit logging

Belum sepenuhnya lengkap untuk model RBAC yang sangat kompleks, tapi struktur dasarnya sudah ada.

---

## 10. Logs

**Status: DONE**

Halaman `logs` mendukung:

* journalctl viewer
* Filter level INFO / WARN / ERROR / ALL
* Search keyword
* Jumlah baris configurable

---

## 11. Docker / Container

**Status: DONE**

Halaman `docker` mencakup:

* List container
* Status, CPU, RAM, ports
* Deploy from image
* Start / Stop / Restart
* Detail container
* Live stats
* Logs

---

## 12. Terminal Web

**Status: DONE (limited)**

Halaman `terminal` hanya menjalankan command yang di-whitelist untuk keamanan.

Yang dibolehkan umum:

* uptime
* free -h
* df -h
* ping
* docker ps
* systemctl status
* ps

Tujuan: tetap aman tanpa memberi shell interaktif bebas.

---

## 13. Backup

**Status: DONE**

Halaman `backup` mendukung:

* CRUD backup jobs
* Tipe: panel, directory, config, mysql, postgres
* Schedule cron
* Manual run
* Riwayat eksekusi
* Restore
* Download backup archive
* Retention policy
* Background scheduler

---

## 14. Maintenance

**Status: DONE**

Halaman `maintenance` mencakup:

* Monitor disk, journal size, apt cache, package upgrade
* Cleanup journal dan apt cache
* apt update / upgrade / autoremove
* Reboot server dengan konfirmasi

---

## 15. Access Points Monitoring

**Status: DONE**

Halaman `access-points` memiliki:

* Scan subnet via ARP + ping sweep
* Auto-discover device
* MAC/IP/vendor mapping menggunakan OUI database
* Persistent inventory
* Group management
* Pin device
* Events log
* SSID survey via WiFi adapter
* Background ping monitor
* Auto-scan scheduler

---

## 16. Websites / Local App Management

**Status: DONE**

Halaman `websites` mengelola website dan dev-server lokal, termasuk:

* Daftar aplikasi web
* Runtime: native atau docker
* Build dan deploy local app
* Start/stop service
* Resolve port dan runtime status
* Cloudflare tunnel expose
* Log service
* Dependency management
* Local app sync

Ini adalah salah satu area yang berkembang cukup signifikan dibanding rencana awal.

---

## 17. Remote Computer Management / Agent

**Status: DONE (core implementation)**

Proyek juga sudah memiliki subsistem agent dan komputer terkelola, berupa:

* `agent/panel_agent.py`
* discovery UDP listener dari backend
* `managed_computers` di database
* heartbeat status online/offline
* info OS, IP, MAC, latency, connectivity
* speed test metadata
* AP and network topology mapping

Jadi arah proyek saat ini sudah mulai bergerak ke model hybrid: panel utama + node/komputer remote yang dilaporkan lewat agent.

---

## 18. Topology / Network Correlation

**Status: DONE**

Ada service tambahan untuk menghubungkan:

* access point inventory
* managed computer status
* gateway / path detection
* AP-seen tracking
* server reach detection

Tujuan: melihat perangkat mana yang online, lewat AP apa, dan apakah koneksi tercepat/terbaik.

---

## 19. Roadmap / Next Step

**Status: PLAN**

Fitur yang masih menjadi target lanjutan:

1. RBAC lebih rinci dan permission per modul
2. Audit log viewer UI yang lebih lengkap
3. Alerting dan notifikasi
4. Multi-server orchestration lebih matang
5. Packaging / deployment otomatis untuk server produksi
6. Hardening akses sudo / privilege model

---

## Ringkasan

Project Ubuntu Panel sudah melewati versi “single-server dashboard” dan berkembang menjadi panel operasional yang mencakup:

* server monitoring
* local app management
* network inventory
* access points monitoring
* remote computer/agent support
* backup and maintenance automation

Dengan demikian, dokumentasi lama masih relevan untuk feature dasar, tetapi perlu dilengkapi dengan fitur tambahan yang memang sudah aktif di codebase saat ini.

Yang ada:

* Create web app (pilih folder + command)
* Framework detection otomatis (next, vite, django, laravel, flask, etc.)
* Auto port resolution
* Start / Stop / Restart per app atau per service
* Log viewer per service
* **Go Online** — Cloudflare Quick Tunnel per service (random trycloudflare.com URL)
* Take Offline — stop tunnel
* URL copy ke clipboard
* Monitor loop (auto-detect mati → OFFLINE)

---

## 16. Panel User Management

**Status: DONE**

Halaman `/user-management` — manajemen akun panel.

Yang ada:

* List panel users
* Create user (superadmin only)
* Change role (superadmin only)
* Update profile (name, email, phone)
* Change password
* Delete user
* 3 role: superadmin, admin, viewer
* JWT auth + Bearer token

---

## 17. Computer Management (Panel Agent)

**Status: DONE**

Halaman `/computer-management` — manage komputer remote via agent.

Yang ada:

* List managed computers
* Create computer entry (dapat token)
* Rename computer
* Issue command (restart/shutdown)
* Agent auto-register (LAN, MAC-based)
* Agent heartbeat (flexible auth)
* Agent download script
* Status: hostname, IP, OS, CPU, RAM, internet, latency, agent version, connection type (LAN/WiFi)

---

## 18. Audit Log

**Status: DONE**

Semua action penting dicatat ke `audit_logs`:

* FILE_UPLOAD, FILE_UPLOAD_BATCH, FILE_MKDIR, FILE_DELETE
* USER_CREATE, USER_DELETE
* SERVICE_START, SERVICE_STOP, SERVICE_RESTART
* DOCKER_DEPLOY, DOCKER_ACTION
* FIREWALL_ADD_RULE, FIREWALL_DELETE_RULE
* TERMINAL_EXEC
* Dan lainnya

---

## Yang BELUM ada (rencana masa depan)

| Fitur | Status | Keterangan |
|-------|--------|------------|
| Package Management (apt) | PARTIAL | Update/upgrade ada di Maintenance, tapi belum ada UI install/remove per package |
| Cron Job Management | PLAN | UI untuk manage crontab user |
| Monitoring & Alerting | PLAN | Rule-based alert (CPU > 90%, RAM > 90%, dll) + notifikasi (Telegram/Discord/webhook) |
| Security Dashboard | PLAN | Failed SSH, suspicious IP, Fail2Ban status |
| Scheduled/Email Reports | DONE | Report server, top 5 beban komputer, CCTV, export PDF/CSV, email terjadwal via cron |

---

## Struktur Menu Sidebar Saat Ini

```text
OVERVIEW
├── Dashboard

SYSTEM
├── Services
├── Processes
├── Logs

INFRASTRUCTURE
├── Storage
├── Network
├── Docker
├── Websites

SECURITY
├── Firewall
├── Users

OPERATIONS
├── Backup
├── Maintenance
├── Access Points
├── Terminal

MANAGEMENT
├── Computer Management
├── User Management
```

---

## Arsitektur Saat Ini

```text
Browser
   │
   ▼
Next.js (port 3000) ────── rewrite ──────► FastAPI (port 8000)
   │                                              │
   │                                              ├── psutil (system metrics)
   │                                              ├── subprocess (systemd, ufw, docker, apt)
   │                                              ├── Docker SDK (docker API)
   │                                              ├── SQLite (WAL mode)
   │                                              └── threading.Thread (background jobs)
   │
   └── WebSocket ──────────────────────────────► /api/ws/metrics (live data)
```

* Tidak ada PostgreSQL, Redis, atau agent terpisah
* Background jobs: Python daemon threads (backup scheduler, AP monitor, website monitor)
* Cloudflare Quick Tunnel untuk akses online
* Upload file bypass Next.js proxy → langsung ke backend
