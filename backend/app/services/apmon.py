"""Monitor Akses Point via jalur LAN (tanpa akses kontroller/MikroTik).

Cara kerja:
1. ARP sweep tiap subnet target (arp-scan bila tersedia & berhak,
   fallback ping sweep + tabel `ip neigh`).
2. MAC → merk via database OUI IEEE (di-cache di backend/data/oui.txt).
3. Identifikasi AP: keyword merk + probing judul halaman admin HTTP(S)
   (Ruijie/Reyee, Ubiquiti, TP-Link/Omada, dst.) + port manajemen.
4. SSID otomatis: survey WiFi dari adapter lokal (`iw scan` / nmcli),
   cocokkan BSSID == MAC perangkat.
5. Inventory persisten: MAC kunci; tidak terlihat lagi → OFFLINE,
   datanya tetap tampil. Setiap transisi dicatat ke ap_events.
"""

import ipaddress
import logging
import os
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from ..db.database import SessionLocal
from ..db.models import APEvent, APScanTarget, AccessPoint

log = logging.getLogger(__name__)

_lock = threading.Lock()
_scanning = False
_last_scan: datetime | None = None
_last_result = ""
_scan_thread: threading.Thread | None = None

# host maksimum per subnet untuk mencegah scan yang salah ketik
_MAX_HOSTS = 4096

# Ping monitor: tiap device di-ping berkala; gagal N kali berturut-turut
# baru dinyatakan OFFLINE (transisi dicatat ke ap_events).
_PING_INTERVAL = int(os.environ.get("AP_PING_INTERVAL", "15"))
_OFFLINE_AFTER = 4
_miss: dict[str, int] = {}  # MAC -> jumlah ping gagal berturut-turut

# ------------------------------------------------------------ OUI lookup
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_OUI_FILE = _DATA_DIR / "oui.txt"
# Server kantor sering tanpa akses internet — file juga bisa diisi
# manual (unduh dari mesin lain): IEEE oui.txt ATAU manuf wireshark.
_OUI_URLS = (
    "https://standards-oui.ieee.org/oui/oui.txt",
    "https://raw.githubusercontent.com/wireshark/wireshark/master/manuf",
)
_oui_map: dict[str, str] = {}
_oui_loaded = False

# cadangan minimal bila semua sumber OUI tidak tersedia
_EMBEDDED_OUI = {
    "D43D7E": "Ruijie Networks",
    "58696C": "Ruijie Networks",
    "F898B9": "Ruijie Networks",
    "0023CD": "TP-LINK",
    "24A43C": "Ubiquiti Networks",
    "788A20": "Ubiquiti Networks",
    "FCECDA": "Ubiquiti Networks",
}

# keyword penanda access point pada merk/judul halaman admin
_AP_KEYWORDS = (
    "ruijie", "reyee", "ubiquiti", "unifi", "tplink", "tp-link",
    "omada", "cisco", "aruba", "ruckus", "huawei", "h3c", "d-link",
    "dlink", "netgear", "engenius", "linksys", "mercusys", "totolink",
    "tenda", "mikrotik", "cambium", "mimosa", "zyxel", "fortinet",
    "wireless", "access point",
)


def _load_oui() -> None:
    global _oui_loaded
    if _oui_loaded:
        return
    with _lock:
        if _oui_loaded:
            return
        # 1) cache lokal — dukung format IEEE ("D43D7E(base 16)\tNama")
        #    dan format wireshark manuf ("40:C2:BA\tNama\tSingkatan")
        if _OUI_FILE.exists():
            try:
                for line in _OUI_FILE.read_text(errors="replace").splitlines():
                    m = re.match(r"^\s*([0-9A-F]{6})\s*\(base 16\)\s*(.+)$", line)
                    if m:
                        _oui_map[m.group(1)] = m.group(2).strip()
                        continue
                    m = re.match(r"^([0-9A-Fa-f]{2}[:-]){2}[0-9A-Fa-f]{2}\s+([^\t]+)", line)
                    if m:
                        key = m.group(0).split()[0].replace(":", "").replace("-", "").upper()
                        _oui_map[key] = m.group(2).strip()
            except OSError:
                pass
        # 2) database nmap / arp-scan bila ada
        for alt in (
            "/usr/share/nmap/nmap-mac-prefixes",
            "/usr/share/arp-scan/ieee-oui.txt",
        ):
            p = Path(alt)
            if not p.exists() or _oui_map:
                continue
            try:
                for line in p.read_text(errors="replace").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(None, 1)
                    if len(parts) == 2 and re.fullmatch(r"[0-9A-Fa-f]{6}", parts[0]):
                        _oui_map[parts[0].upper()] = parts[1]
            except OSError:
                pass
        _oui_map.update(_EMBEDDED_OUI)
        _oui_loaded = True


def _refresh_oui_async() -> None:
    """Unduh database IEEE sekali (cache 30 hari) di background."""

    def _worker() -> None:
        try:
            if _OUI_FILE.exists() and (
                time.time() - _OUI_FILE.stat().st_mtime < 30 * 86400
            ):
                return
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = _OUI_FILE.with_suffix(".tmp")
            for url in _OUI_URLS:
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "ubuntu-panel"}
                    )
                    with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as f:
                        f.write(r.read())
                    tmp.replace(_OUI_FILE)
                    globals()["_oui_loaded"] = False  # paksa reload
                    _load_oui()
                    return
                except Exception:  # noqa: BLE001 — coba mirror berikutnya
                    continue
        except Exception:  # noqa: BLE001 — unduhan gagal = pakai cache lama
            pass

    threading.Thread(target=_worker, daemon=True, name="oui-refresh").start()


def oui_vendor(mac: str) -> str:
    _load_oui()
    key = mac.upper().replace(":", "").replace("-", "")[:6]
    return _oui_map.get(key, "")


# ------------------------------------------------------------ discovery
def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _priv(cmd: list[str]) -> list[str]:
    return cmd if _is_root() else ["sudo", "-n"] + cmd


def _parse_cidr(cidr: str):
    try:
        net = ipaddress.ip_network(cidr.strip(), strict=False)
    except ValueError:
        raise ValueError(f"CIDR tidak valid: {cidr}")
    if net.num_addresses > _MAX_HOSTS:
        raise ValueError(
            f"Subnet terlalu besar ({net.num_addresses} host); maksimal {_MAX_HOSTS}"
        )
    return net


# ------------------------------------------------- progres scan (UI)

def _discover_arp_scan(cidr: str) -> dict[str, str]:
    """ARP sweep via arp-scan; butuh root/CAP_NET_RAW. Peta IP -> MAC."""
    exe = shutil.which("arp-scan")
    if not exe:
        return {}
    cmd = [exe, "--retry=1", "--quiet", cidr]
    try:
        proc = subprocess.run(
            _priv(cmd), capture_output=True, text=True, timeout=60
        )
    except (subprocess.TimeoutExpired, OSError):
        return {}
    if proc.returncode != 0:
        return {}
    macs: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        m = re.match(
            r"^(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F:]{17})", line.strip()
        )
        if m:
            macs[m.group(1)] = m.group(2).lower()
    return macs


def _neigh_macs() -> dict[str, str]:
    """Peta IP -> MAC dari tabel neighbor kernel."""
    try:
        out = subprocess.run(
            ["ip", "neigh", "show"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:  # noqa: BLE001
        return {}
    neigh: dict[str, str] = {}
    for line in out.splitlines():
        # format: "<IP> dev <IFACE> lladdr <MAC> <STATE>"
        parts = line.split()
        if len(parts) >= 5 and "lladdr" in parts:
            i = parts.index("lladdr")
            if i + 1 < len(parts):
                neigh[parts[0]] = parts[i + 1].lower()
    return neigh


def _ping_host(ip: str) -> bool:
    try:
        return (
            subprocess.run(
                ["ping", "-c", "1", "-W", "2", ip],
                capture_output=True,
                timeout=4,
            ).returncode
            == 0
        )
    except Exception:  # noqa: BLE001
        return False


def _ping_host_alive(ip: str) -> str | None:
    return ip if _ping_host(ip) else None


def discover_hosts(cidr: str, on_progress=None) -> list[tuple[str, str | None]]:
    """Ping sweep paralel dengan progres NYATA per host (0..total).

    MAC hanya tersedia bila host berada di segmen L2 yang sama
    (arp-scan / ip neigh). Host lintas router tetap tercatat dan
    akan memakai kunci `ip-<addr>` di inventory.
    """
    net = _parse_cidr(cidr)
    ips = [str(h) for h in net.hosts()]
    total = len(ips)

    def _tick(done: int) -> None:
        if on_progress:
            on_progress(done, total)

    # fase sweep — ping semua host, progres naik tiap ping selesai
    done = 0
    alive: set[str] = set()
    with ThreadPoolExecutor(max_workers=64) as pool:
        futures = {pool.submit(_ping_host_alive, ip): ip for ip in ips}
        for fut in as_completed(futures):
            done += 1
            ip = fut.result()
            if ip:
                alive.add(ip)
            _tick(done)

    # fase mac — arp-skan cepat lalu/ne tabel neighbor
    if on_progress:
        on_progress(total, total)
    macs = _discover_arp_scan(cidr)
    for ip, mac in _neigh_macs().items():
        macs.setdefault(ip, mac)
    if not alive:
        # ping diblok semua tapi ARP menjawab — pakai hasil ARP
        alive = set(macs.keys())

    hosts: list[tuple[str, str | None]] = []
    seen_keys: set[str] = set()
    for ip in sorted(alive):
        mac = macs.get(ip)
        mac = None if (not mac or mac == "00:00:00:00:00:00") else mac
        key = mac or f"ip-{ip}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        hosts.append((ip, mac))
    return hosts


# ------------------------------------------------------- probing & SSID
def _probe_http_title(ip: str) -> str:
    """Judul halaman admin (http/https) — sering memuat model AP."""
    titles = []
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for scheme in ("http", "https"):
        try:
            req = urllib.request.Request(
                f"{scheme}://{ip}/",
                headers={"User-Agent": "Mozilla/5.0 (ubuntu-panel)"},
            )
            with urllib.request.urlopen(req, timeout=2, context=ctx) as r:
                body = r.read(4096).decode("utf-8", errors="replace")
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
            if m and m.group(1).strip():
                titles.append(m.group(1).strip()[:200])
                break
        except Exception:  # noqa: BLE001 — port tertutup/tidak web
            continue
    return " | ".join(titles)


def wifi_iface() -> str:
    """Nama adapter WiFi lokal bila ada (untuk survey SSID otomatis)."""
    for p in Path("/sys/class/net").glob("*/wireless"):
        return p.parent.name
    return ""


def _wifi_survey() -> dict[str, str]:
    """Peta BSSID → SSID dari adapter WiFi lokal (butuh hak scan)."""
    result: dict[str, str] = {}

    iface = wifi_iface()
    if iface:
        try:
            out = subprocess.run(
                _priv(["iw", "dev", iface, "scan"]),
                capture_output=True,
                text=True,
                timeout=30,
            )
            bssid = ssid = ""
            for line in out.stdout.splitlines():
                m = re.match(r"\s*BSS\s+([0-9a-fA-F:]{17})", line)
                if m:
                    if bssid and ssid:
                        result[bssid.lower()] = ssid
                    bssid, ssid = m.group(1), ""
                    continue
                if bssid:
                    s = re.match(r"\s*SSID:\s*(.*)$", line)
                    if s and not ssid:
                        ssid = s.group(1).strip()
            if bssid and ssid:
                result[bssid.lower()] = ssid
        except Exception:  # noqa: BLE001
            pass

    if not result and shutil.which("nmcli"):
        try:
            out = subprocess.run(
                ["nmcli", "-t", "-f", "BSSID,SSID", "dev", "wifi", "list"],
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout
            for line in out.splitlines():
                # format terse: AA\:BB\:…\:FF\:SSID (koma aman, titik dua di-escape)
                m = re.match(r"^((?:[0-9A-Fa-f]{2}\\?:){5}[0-9A-Fa-f]{2})\\?:(.*)$", line)
                if m:
                    bssid = m.group(1).replace("\\", "").lower()
                    if bssid.count(":") == 5:
                        result[bssid] = m.group(2).strip()
        except Exception:  # noqa: BLE001
            pass
    return result


def _classify(vendor: str, title: str) -> tuple[bool, str]:
    """(is_ap, model) dari merk + judul halaman admin."""
    hay = f"{vendor} {title}".lower()
    is_ap = any(k in hay for k in _AP_KEYWORDS)
    model = ""
    # pola umum kode model: RG-APxxx, EAPxxx, UAP-xxx, CAPxxx, dst.
    m = re.search(
        r"\b((?:RG|EAP|UAP|CAP|AP|WAP|NWA|EWS)[-_ ]?[A-Z0-9]{2,}[-_]?[A-Z0-9]*)\b",
        title,
        re.I,
    )
    if m:
        model = m.group(1).upper()
    elif title:
        model = title.split("|")[0].split("-")[0].strip()[:64]
    return is_ap, model


# ------------------------------------------------------------- scan run
_scan_progress: dict = {"running": False}


def _progress_snapshot() -> dict:
    return dict(_scan_progress)


def _progress_set(**kw) -> None:
    """Update state progres scan — dibaca UI via status_summary."""
    _scan_progress.update(kw)


def _progress_reset() -> None:
    _scan_progress.clear()
    _scan_progress["running"] = False


def _key_of(ip: str, mac: str | None) -> str:
    """Kunci inventory: MAC asli, atau ip-<addr> bila MAC tak terbaca."""
    return mac if mac else f"ip-{ip}"


def _upsert(
    db,
    found: list[tuple[str, str | None]],
    ssids: dict[str, str],
    titles: dict[str, str],
    ip_segment: dict[str, str] | None = None,
) -> dict:
    """Discovery-only upsert — TANPA kerja jaringan, transaksi cepat.

    Status online/offline dikelola ping monitor. `titles` sudah diprobe
    sebelumnya di _do_scan agar transaksi tidak terbuka saat menunggu HTTP.
    Device lintas-segment tanpa MAC disimpan berkunci `ip-<addr>`.
    `ip_segment`: mapping IP → segment label dari subnet target.
    """
    now = datetime.utcnow()
    stats = {"discovered": 0, "online": 0}
    all_aps = db.query(AccessPoint).all()
    existing_by_mac = {ap.mac.lower(): ap for ap in all_aps}
    existing_by_ip = {ap.ip: ap for ap in all_aps}
    ip_seg = ip_segment or {}

    for ip, mac in found:
        key = _key_of(ip, mac).lower()
        vendor = oui_vendor(mac) if mac else ""
        title = titles.get(key, "")
        is_ap, model = _classify(vendor, title)
        ssid = ssids.get(key, "")
        segment = ip_seg.get(ip, "")

        ap = existing_by_mac.get(key)

        # 1. Jika belum ada by MAC, tapi ada placeholder ip-<ip> sebelumnya di database -> merge!
        placeholder_key = f"ip-{ip}".lower()
        if ap is None and mac and placeholder_key in existing_by_mac:
            placeholder_ap = existing_by_mac.pop(placeholder_key)
            placeholder_ap.mac = mac.lower()
            existing_by_mac[mac.lower()] = placeholder_ap
            ap = placeholder_ap

        # 2. Jika masih belum ada, cek apakah ada entri unpinned dengan IP yang sama
        if ap is None and ip in existing_by_ip:
            cand = existing_by_ip[ip]
            if not cand.pinned and cand.group_id is None and not cand.notes:
                ap = cand
                if mac and cand.mac.lower() in existing_by_mac:
                    existing_by_mac.pop(cand.mac.lower())
                ap.mac = key
                existing_by_mac[key] = ap

        if ap is None:
            ap = AccessPoint(
                mac=key, ip=ip, vendor=vendor, model=model, ssid=ssid,
                is_ap=is_ap, segment=segment,
                status="ONLINE", first_seen=now, last_seen=now,
            )
            db.add(ap)
            db.flush()
            existing_by_mac[key] = ap
            existing_by_ip[ip] = ap
            db.add(APEvent(ap_id=ap.id, mac=key, ip=ip, event="DISCOVERED"))
            stats["discovered"] += 1
        else:
            changed_status = ap.status != "ONLINE"
            ap.ip, ap.vendor, ap.last_seen = ip, vendor or ap.vendor, now
            _miss[ap.mac] = 0
            ap.status = "ONLINE"
            if title and not ap.model:
                ap.model = model
            if ssid and not ap.ssid:
                ap.ssid = ssid
            if is_ap:
                ap.is_ap = True
            if segment:
                ap.segment = segment
            if changed_status:
                db.add(APEvent(ap_id=ap.id, mac=ap.mac, ip=ip, event="ONLINE"))
        stats["online"] += 1

    db.commit()
    return stats


def _do_scan() -> dict:
    """Scan semua target sekali (asumsi flag _scanning sudah dipegang).

    Semua aktivitas jaringan (survey WiFi, sweep subnet, probe HTTP)
    dilakukan TANPA transaksi DB terbuka supaya ping monitor & endpoint
    lain tidak terblokir lock SQLite.
    """
    global _last_scan, _last_result

    # fase 1 — baca target & model yang dikenal (transaksi singkat)
    db = SessionLocal()
    try:
        target_rows = db.query(APScanTarget.cidr, APScanTarget.label).all()
        targets = [t.cidr for t in target_rows]
        # mapping subnet label: cidr → label (untuk auto-classify device)
        subnet_labels = {t.cidr: (t.label or "") for t in target_rows}
        known_keys = {
            k for k, in db.query(AccessPoint.mac).all()
        }
    finally:
        db.close()
    if not targets:
        _last_result = "no subnet targets"
        _progress_reset()
        return {"skipped": True, "reason": _last_result}

    # fase 2 — jaringan, tanpa transaksi terbuka
    ssids_by_bssid = _wifi_survey()
    errors: list[str] = []
    found_all: list[tuple[str, str | None]] = []
    seen_keys: set[str] = set()

    def _on_progress(done: int, total: int) -> None:
        _progress_set(done=done, total=total)

    n_targets = len(targets)
    for idx, cidr in enumerate(targets):
        try:
            _progress_set(
                running=True, cidr=cidr, target_index=idx + 1,
                targets_total=n_targets, done=0, total=256, found=len(found_all),
                phase="sweep",
            )
            for ip, mac in discover_hosts(cidr, on_progress=_on_progress):
                key = _key_of(ip, mac)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                found_all.append((ip, mac))
                _progress_set(phase="arp", found=len(found_all))
        except ValueError as e:
            errors.append(str(e))
        except Exception as e:  # noqa: BLE001 — satu subnet gagal tak boleh menghentikan lainnya
            errors.append(f"{cidr}: {e}")
            log.warning("scan %s failed: %s", cidr, e)

    _progress_set(phase="probe", done=0, total=0, found=len(found_all))

    need_probe = [
        (ip, key) for ip, mac in found_all
        if (key := _key_of(ip, mac)) not in known_keys
    ]
    titles: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=32) as pool:
        for (ip, key), title in zip(
            need_probe, pool.map(lambda p: _probe_http_title(p[0]), need_probe)
        ):
            titles[key] = title

    # fase 3 — tulis (transaksi singkat)
    _progress_set(phase="write")

    # bangun mapping IP → segment berdasarkan subnet label
    ip_segment: dict[str, str] = {}
    for cidr, label in subnet_labels.items():
        if not label:
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            for ip, _mac in found_all:
                try:
                    if ipaddress.ip_address(ip) in net:
                        ip_segment.setdefault(ip, label)
                except ValueError:
                    pass
        except ValueError:
            pass

    total = {"discovered": 0, "online": 0}
    db = SessionLocal()
    try:
        stats = _upsert(db, found_all, ssids_by_bssid, titles, ip_segment)
        for k in total:
            total[k] += stats[k]
    finally:
        db.close()

    _last_scan = datetime.utcnow()
    _last_result = (
        f"{total['discovered']} new, {total['online']} seen"
        + (f" | {len(errors)} errors" if errors else "")
    )
    _progress_reset()
    return {"stats": total, "errors": errors}


def run_scan() -> dict:
    """Scan semua target; dipanggil scheduler."""
    global _scanning
    with _lock:
        if _scanning:
            return {"skipped": True}
        _scanning = True
    try:
        return _do_scan()
    finally:
        with _lock:
            _scanning = False
        _progress_reset()


def scan_now() -> bool:
    """Trigger scan manual di background; False bila sedang berjalan."""
    global _scan_thread, _scanning
    with _lock:
        if _scanning:
            return False
        _scanning = True  # flag dipegang sejak sekarang — tanpa race window

    def _worker() -> None:
        try:
            _do_scan()
        except Exception:  # noqa: BLE001
            log.exception("manual scan failed")
        finally:
            _progress_reset()
            with _lock:
                globals()["_scanning"] = False

    _scan_thread = threading.Thread(target=_worker, daemon=True, name="ap-scan-now")
    _scan_thread.start()
    return True


def _scheduler_loop(interval: int) -> None:
    while True:
        time.sleep(interval)
        try:
            run_scan()
        except Exception:  # noqa: BLE001 — scheduler tidak boleh mati
            log.exception("scheduled scan failed")


# ------------------------------------------------------------ ping monitor
def _monitor_once() -> dict:
    """Ping semua device inventory sekali; transisi status dicatat.

    Transaksi DB ditahan sesingkat mungkin: snapshot baca -> tutup,
    ping TANPA transaksi terbuka, lalu tulis cepat. Tanpa ini, commit
    monitor bisa kena "database is locked" saat discovery scan berjalan.
    """
    # fase 1 — snapshot singkat
    db = SessionLocal()
    try:
        devices = [
            {"id": ap.id, "mac": ap.mac, "ip": ap.ip}
            for ap in db.query(
                AccessPoint.id, AccessPoint.mac, AccessPoint.ip
            ).all()
        ]
    finally:
        db.close()
    if not devices:
        return {"online": 0, "offline": 0}

    # fase 2 — ping tanpa transaksi terbuka
    def _alive(d: dict) -> str | None:
        return d["mac"] if _ping_host(d["ip"]) else None

    with ThreadPoolExecutor(max_workers=128) as pool:
        alive_macs = {m for m in pool.map(_alive, devices) if m}

    # fase 3 — tulis cepat (transaksi milidetik)
    now = datetime.utcnow()
    stats = {"online": 0, "offline": 0}
    db = SessionLocal()
    try:
        rows = {ap.id: ap for ap in db.query(AccessPoint).all()}
        for d in devices:
            mac = d["mac"]
            ap = rows.get(d["id"])
            if ap is None:  # terhapus di antara fase
                continue
            if mac in alive_macs:
                _miss[mac] = 0
                ap.last_seen = now
                if ap.status != "ONLINE":
                    ap.status = "ONLINE"
                    db.add(APEvent(
                        ap_id=ap.id, mac=ap.mac, ip=ap.ip, event="ONLINE"
                    ))
                    stats["online"] += 1
            else:
                n = _miss.get(mac, 0) + 1
                _miss[mac] = n
                if n >= _OFFLINE_AFTER and ap.status != "OFFLINE":
                    ap.status = "OFFLINE"
                    db.add(APEvent(
                        ap_id=ap.id, mac=ap.mac, ip=ap.ip, event="OFFLINE"
                    ))
                    stats["offline"] += 1

        # Jaga agar tabel ap_events tidak membengkak puluhan ribu baris
        try:
            event_count = db.query(APEvent).count()
            if event_count > 2500:
                oldest_keep = (
                    db.query(APEvent.id)
                    .order_by(APEvent.id.desc())
                    .offset(1500)
                    .first()
                )
                if oldest_keep:
                    db.query(APEvent).filter(APEvent.id < oldest_keep[0]).delete(
                        synchronize_session=False
                    )
        except Exception:
            pass

        db.commit()
        return stats
    finally:
        db.close()


def prune_stale_devices(db, days: int = 7) -> int:
    """Hapus perangkat offline yang tidak di-pin, tanpa grup, tanpa catatan,
    dan tidak pernah terlihat selama lebih dari `days` hari."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = db.query(AccessPoint).filter(
        AccessPoint.pinned.is_(False),
        AccessPoint.group_id.is_(None),
        (AccessPoint.notes == "") | AccessPoint.notes.is_(None),
        AccessPoint.status == "OFFLINE",
        AccessPoint.last_seen < cutoff,
    )
    deleted_ids = [ap.id for ap in q.all()]
    if not deleted_ids:
        return 0
    # Hapus event terkait
    db.query(APEvent).filter(APEvent.ap_id.in_(deleted_ids)).delete(synchronize_session=False)
    count = db.query(AccessPoint).filter(AccessPoint.id.in_(deleted_ids)).delete(synchronize_session=False)
    db.commit()
    return count


def _monitor_loop(interval: int) -> None:
    while True:
        time.sleep(interval)
        try:
            _monitor_once()
        except Exception:  # noqa: BLE001 — monitor tidak boleh mati
            log.warning("ping monitor cycle failed", exc_info=True)


def start_monitor() -> None:
    threading.Thread(
        target=_monitor_loop, args=(_PING_INTERVAL,), daemon=True,
        name="ap-ping-monitor",
    ).start()


def start_scheduler() -> None:
    interval = int(os.environ.get("AP_SCAN_INTERVAL", "300"))
    threading.Thread(
        target=_scheduler_loop, args=(interval,), daemon=True, name="ap-scheduler"
    ).start()
    start_monitor()
    _refresh_oui_async()


# ---------------------------------------------------------------- status
def status_summary(db) -> dict:
    aps = db.query(AccessPoint).all()
    return {
        "total": len(aps),
        "online": sum(1 for a in aps if a.status == "ONLINE"),
        "offline": sum(1 for a in aps if a.status == "OFFLINE"),
        "aps": sum(1 for a in aps if a.is_ap),
        "pinned": sum(1 for a in aps if a.pinned),
        "scanning": _scanning,
        "scan_progress": _progress_snapshot(),
        "last_scan": _last_scan.isoformat() + "Z" if _last_scan else None,
        "last_result": _last_result,
        # info ping monitor untuk UI
        "ping_interval": _PING_INTERVAL,
        "offline_after": _OFFLINE_AFTER,
        # SSID otomatis hanya jalan bila server punya adapter WiFi
        "wifi_iface": wifi_iface(),
    }
